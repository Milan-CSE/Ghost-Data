"""Unit tests for all evidence format adapters using real fixtures (test_adapters.py)."""
from __future__ import annotations
from pathlib import Path
import pytest
from ghost.adapters import (
    sqlite_dump,
    json_bundle,
    json_ledger,
    log_kv,
    log_syslog,
    log_jsonl,
    handover_txt,
    pdf_text,
    png_vision,
    parse_evidence_file,
)
from ghost.types import State

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_sqlite_dump_adapter():
    """Verify SQLite dump parses tables, extracts identifiers, and flags covers_system=True."""
    sql_path = FIXTURES_DIR / "excerpt.sql"
    facts = sqlite_dump.parse(sql_path, file_id="ev_sql_01", captured_at="2026-09-02T23:00:00Z")

    assert len(facts) >= 2
    res_ids = {f.resource_id: f for f in facts}

    assert "account_005" in res_ids
    f_005 = res_ids["account_005"]
    assert f_005.system_id == "account_service"
    assert f_005.category == "USER_PROFILE"
    assert f_005.state == State.PRESENT
    assert "user_05" in f_005.user_ids
    assert "leila.haddad@yahoo.com" in f_005.emails
    assert f_005.covers_system is True
    assert f_005.store == "customer_profiles_failover_replica"


def test_json_bundle_adapter():
    """Verify JSON snapshot bundle evaluates inner snapshot timestamps and covers_system=True."""
    bundle_path = FIXTURES_DIR / "excerpt_bundle.json"
    facts = json_bundle.parse(bundle_path, file_id="ev_bundle_01", captured_at="2026-01-31T12:00:00Z")

    res_ids = {f.resource_id: f for f in facts}

    # Inner snapshot 1 captured at 2026-01-29T12:00:00Z
    assert "account_2424" in res_ids
    f_acc = res_ids["account_2424"]
    assert f_acc.captured_at == "2026-01-29T12:00:00Z"
    assert f_acc.state == State.PRESENT
    assert f_acc.covers_system is True

    # Tombstone extraction
    assert "tombstone_99" in res_ids
    f_tomb = res_ids["tombstone_99"]
    assert f_tomb.category == "ACCOUNT_TOMBSTONE"
    assert f_tomb.state == State.REDACTED

    # Inner snapshot 2 captured at 2026-01-30T10:00:00Z
    assert "analytics_131" in res_ids
    f_ana = res_ids["analytics_131"]
    assert f_ana.captured_at == "2026-01-30T10:00:00Z"
    assert f_ana.state == State.PRESENT

    # Anonymized analytics profile
    assert "analytics_999" in res_ids
    f_anon = res_ids["analytics_999"]
    assert f_anon.state == State.ANONYMIZED


def test_json_ledger_adapter():
    """Verify JSON ledger and service exports parse records and status_codes."""
    ledger_path = FIXTURES_DIR / "excerpt_ledger.json"
    facts = json_ledger.parse(ledger_path, file_id="ev_ledger_01", captured_at="2026-08-12T09:00:00Z")

    res_ids = {f.resource_id: f for f in facts}

    # NOT_FOUND record
    assert "account_1084" in res_ids
    assert res_ids["account_1084"].state == State.ABSENT

    # Active data flow
    assert "data_flow_101" in res_ids
    assert res_ids["data_flow_101"].state == State.ACTIVE

    # 404 profile lookup in service_exports
    assert "account_470" in res_ids
    assert res_ids["account_470"].state == State.ABSENT

    # Backup restore entry
    assert "backup_3382" in res_ids
    assert res_ids["backup_3382"].state == State.ACTIVE


def test_log_kv_adapter():
    """Verify key-value log parser maps 404/NOT_FOUND to ABSENT and enabled=true to ACTIVE."""
    kv_path = FIXTURES_DIR / "excerpt_kv.log"
    facts = log_kv.parse(kv_path, file_id="ev_kv_01", captured_at="2026-03-15T07:00:00Z")

    res_ids = {f.resource_id: f for f in facts}

    assert "account_022" in res_ids
    assert res_ids["account_022"].state == State.ABSENT

    assert "account_1538" in res_ids
    assert res_ids["account_1538"].state == State.PRESENT

    assert "data_flow_3669" in res_ids
    assert res_ids["data_flow_3669"].state == State.ACTIVE
    assert res_ids["data_flow_3669"].system_id == "integration_service"

    # Observation-level check
    assert res_ids["account_022"].covers_system is False


def test_log_syslog_adapter():
    """Verify syslog parser extracts message/attachment pii scans and 404 status."""
    syslog_path = FIXTURES_DIR / "excerpt_syslog.log"
    facts = log_syslog.parse(syslog_path, file_id="ev_syslog_01", captured_at="2026-03-25T08:51:13Z")

    res_ids = {f.resource_id: f for f in facts}

    assert "support_9464" in res_ids
    assert res_ids["support_9464"].category == "SUPPORT_MESSAGE"
    assert res_ids["support_9464"].state == State.PRESENT

    assert "account_7606" in res_ids
    assert res_ids["account_7606"].state == State.ABSENT  # rows="0" http_status="404"

    assert "support_2944" in res_ids
    assert res_ids["support_2944"].category == "SUPPORT_ATTACHMENT"


def test_log_jsonl_adapter():
    """Verify structured JSONL log parser extracts hits, misses, and identifiers."""
    jsonl_path = FIXTURES_DIR / "excerpt_jsonl.log"
    facts = log_jsonl.parse(jsonl_path, file_id="ev_jsonl_01", captured_at="2026-04-19T06:51:21Z")

    res_ids = {f.resource_id: f for f in facts}

    assert "search_9365" in res_ids
    assert res_ids["search_9365"].system_id == "search_service"
    assert res_ids["search_9365"].state == State.PRESENT

    assert "support_5609" in res_ids
    assert "lpereira7245@gmail.com" in res_ids["support_5609"].emails

    assert "account_101" in res_ids
    assert res_ids["account_101"].state == State.ABSENT  # result="miss", http_status=404


def test_handover_txt_adapter():
    """Verify shift handover table parses pipe-delimited records."""
    handover_path = FIXTURES_DIR / "excerpt_handover.txt"
    facts = handover_txt.parse(handover_path, file_id="ev_txt_01", captured_at="2026-10-01T12:00:00Z")

    res_ids = {f.resource_id: f for f in facts}

    assert "account_146" in res_ids
    assert res_ids["account_146"].state == State.ABSENT

    assert "account_1810" in res_ids
    assert res_ids["account_1810"].state == State.PRESENT

    assert "data_flow_500" in res_ids
    assert res_ids["data_flow_500"].state == State.DISABLED


def test_pdf_text_adapter():
    """Verify PDF adapter extracts text and resource identifiers."""
    pdf_path = FIXTURES_DIR / "excerpt.pdf"
    facts = pdf_text.parse(pdf_path, file_id="ev_pdf_01", captured_at="2026-05-20T10:00:00Z")

    assert len(facts) >= 1
    assert any("support" in f.system_id for f in facts)


def test_pdf_support_attachment_order_number_exclusion():
    """Regression test: PDF adapter must extract valid platform resources (support_001)

    and must NOT treat transactional order numbers (ORD-xxxx) as resources.
    """
    real_pdf = Path("dataset/evidence/documents/delivery_correction_attachment.pdf")
    if real_pdf.exists():
        facts = pdf_text.parse(real_pdf, file_id="evidence_58", captured_at="2026-09-12T07:30:00Z")
        res_ids = {f.resource_id for f in facts}
        assert "support_001" in res_ids
        assert not any(r.startswith("ORD-") for r in res_ids), f"Unexpected ORD- resources extracted: {res_ids}"


def test_png_vision_adapter_contract():
    """Verify PNG vision adapter parses structured payload without requiring live credentials."""
    mock_payload = [
        {
            "resource_id": "account_admin_99",
            "system_id": "account_service",
            "category": "USER_PROFILE",
            "state": "PRESENT",
            "email": "admin.view@example.com",
            "user_id": "user_777",
        }
    ]
    facts = png_vision.parse_vision_payload(mock_payload, file_id="ev_png_01", captured_at="2026-09-01T10:00:00Z")
    assert len(facts) == 1
    assert facts[0].resource_id == "account_admin_99"
    assert facts[0].state == State.PRESENT


def test_router_dispatch():
    """Verify parse_evidence_file routes files correctly by extension."""
    sql_path = FIXTURES_DIR / "excerpt.sql"
    facts = parse_evidence_file(sql_path, "ev_sql_01", "2026-09-02T23:00:00Z")
    assert len(facts) >= 2

    bundle_path = FIXTURES_DIR / "excerpt_bundle.json"
    facts_bundle = parse_evidence_file(bundle_path, "ev_bundle_01", "2026-01-31T12:00:00Z")
    assert len(facts_bundle) >= 3
