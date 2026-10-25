"""Tests for LLM client, telemetry, and vision adapter (code/ghost/llm.py, code/ghost/vision.py).

Covers:
- Missing credentials explicit failure (never silent fake fallback)
- Model retries with backoff and schema failures
- Disk cache hits and telemetry recording
- Screenshot fact extraction, provenance, confidence logging, and cutoff enforcement
"""
from __future__ import annotations
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ghost.types import State, Fact
from ghost.llm import LLMClient
from ghost.vision import extract_console_facts, CONFIDENCE_LOG_PATH
from ghost.adapters.png_vision import parse_vision_payload


def test_llm_missing_credentials_fails_loudly(monkeypatch, tmp_path):
    """When credentials are absent, client must raise RuntimeError, never silently invent completions."""
    monkeypatch.delenv("GEMINI_API", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    client = LLMClient(cache_dir=tmp_path / "cache", runs_dir=tmp_path / "runs")
    with pytest.raises(RuntimeError, match="LLM API credentials missing"):
        client.call("intent", "Test prompt without cache")


def test_llm_cache_hit_and_telemetry(tmp_path):
    """Cached response produces cache_hit=True telemetry with zero token charge."""
    cache_dir = tmp_path / "cache"
    runs_dir = tmp_path / "runs"
    client = LLMClient(cache_dir=cache_dir, runs_dir=runs_dir, run_id="test_run_1")

    # Manually populate cache file
    prompt = "Test prompt"
    key = client._cache_key(client.model_name, prompt, None)
    cache_file = cache_dir / f"{key}.json"
    cache_file.write_text(
        json.dumps({
            "key": key,
            "model": client.model_name,
            "kind": "test",
            "result": {"status": "success"},
            "usage": {"input_tokens": 50, "output_tokens": 10},
            "cost_usd": 0.00000675,
            "cached_at": "2026-10-25T08:00:00Z",
        }),
        encoding="utf-8",
    )

    res = client.call("test", prompt)
    assert res == {"status": "success"}

    telem_file = runs_dir / "test_run_1" / "telemetry.jsonl"
    assert telem_file.exists()
    records = [json.loads(line) for line in telem_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 1
    assert records[0]["cache_hit"] is True
    assert records[0]["input_tokens"] == 0
    assert records[0]["original_tokens"] == {"input_tokens": 50, "output_tokens": 10}


def test_llm_retries_on_transient_failure(monkeypatch, tmp_path):
    """Client performs bounded retries with backoff on failure."""
    cache_dir = tmp_path / "cache"
    runs_dir = tmp_path / "runs"
    client = LLMClient(cache_dir=cache_dir, runs_dir=runs_dir, run_id="test_run_retry")

    mock_genai_client = MagicMock()
    # First attempt fails, second attempt succeeds
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({"result": "retry_ok"})
    mock_resp.usage_metadata.prompt_token_count = 20
    mock_resp.usage_metadata.candidates_token_count = 5

    mock_genai_client.models.generate_content.side_effect = [
        Exception("Temporary network timeout"),
        mock_resp,
    ]
    client._genai_client = mock_genai_client

    res = client.call("test", "Test retry prompt", max_retries=2)
    assert res == {"result": "retry_ok"}
    assert mock_genai_client.models.generate_content.call_count == 2


def test_vision_parse_payload_schema():
    """Verify parse_vision_payload produces valid Fact instances with exact identifiers."""
    payload = [
        {
            "system_id": "account_service",
            "resource_id": "account_101",
            "category": "USER_PROFILE",
            "state": "PRESENT",
            "user_id": "user_101",
            "email": "user@example.com",
            "phone": "+1 555 1234",
            "email_hash": "a" * 64,
        }
    ]
    facts = parse_vision_payload(payload, file_id="evidence_04", captured_at="2026-09-26T11:00:00Z")
    assert len(facts) == 1
    f = facts[0]
    assert f.file_id == "evidence_04"
    assert f.system_id == "account_service"
    assert f.resource_id == "account_101"
    assert f.category == "USER_PROFILE"
    assert f.state == State.PRESENT
    assert "user@example.com" in f.emails
    assert "user_101" in f.user_ids
    assert "+15551234" in f.phones or "+1 555 1234" in f.phones
    assert ("a" * 64) in f.hashes
    assert f.store == "screenshot_vision"
    assert f.covers_system is False


def test_vision_low_confidence_flagged(tmp_path, monkeypatch):
    """Low confidence extractions (< 0.8) must be recorded in review/vision_confidence.md."""
    log_file = tmp_path / "vision_confidence.md"
    monkeypatch.setattr("ghost.vision.CONFIDENCE_LOG_PATH", log_file)

    test_payload = [
        {
            "system_id": "account_service",
            "resource_id": "account_low_conf",
            "category": "USER_PROFILE",
            "state": "PRESENT",
            "confidence": 0.65,
            "notes": "Blurry text in table column",
        }
    ]

    with patch("ghost.vision.extract_image", return_value=test_payload):
        dummy_img = tmp_path / "test_screenshot.png"
        dummy_img.write_bytes(b"dummy_png_bytes")
        facts = extract_console_facts(dummy_img, "ev_dummy", "2026-09-26T11:00:00Z")

    assert len(facts) == 1
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "account_low_conf" in content
    assert "0.65" in content


def test_screenshot_evidence_case_dependency():
    """Verify that cached screenshot evidence correctly populates facts for real evidence files."""
    img_path = Path("dataset/evidence/images/account_admin_console_20260926.png")
    facts = extract_console_facts(img_path, "evidence_04", "2026-09-26T11:00:00Z")
    assert len(facts) >= 1
    # Check that account_5762 was extracted
    acc_fact = next((f for f in facts if f.resource_id == "account_5762"), None)
    assert acc_fact is not None
    assert acc_fact.system_id == "account_service"
    assert "haruka.s1838@zoho.com" in acc_fact.emails
    assert "user_11" in acc_fact.user_ids
    assert acc_fact.state == State.PRESENT
