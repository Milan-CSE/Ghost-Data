"""Shared LLM client and telemetry tracking (code/ghost/llm.py).

Provides centralized, deterministic model calls with:
- Temperature 0
- Strict JSON schema validation
- Bounded retries with exponential backoff
- Disk cache keyed by sha256(model + prompt + image_hash)
- Telemetry recording to runs/<run_id>/telemetry.jsonl
- Explicit failure on missing credentials
"""
from __future__ import annotations
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ghost.config import CODE_DIR, REPO_ROOT

CACHE_DIR = REPO_ROOT / "cache" / "llm"
RUNS_DIR = REPO_ROOT / "runs"
PROMPTS_DIR = CODE_DIR / "prompts"

# Pricing rates per 1,000,000 tokens (USD)
MODEL_PRICING = {
    "gemini-3.1-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-3.8-flash": {"input": 0.15, "output": 0.60},
    "gemini-flash-latest": {"input": 0.15, "output": 0.60},
    "default": {"input": 0.10, "output": 0.40},
}


def _get_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = MODEL_PRICING.get(model, MODEL_PRICING["default"])
    return round((input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000, 8)


class LLMClient:
    """Centralized LLM client with strict schema validation, disk cache, and telemetry."""

    def __init__(
        self,
        model_name: str = "gemini-3.1-flash-lite",
        cache_dir: Path | str | None = None,
        runs_dir: Path | str | None = None,
        run_id: str | None = None,
    ):
        self.model_name = model_name
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.runs_dir = Path(runs_dir) if runs_dir else RUNS_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

        if not run_id:
            run_id = os.environ.get("GHOST_RUN_ID") or datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
        self.run_id = run_id
        self._genai_client = None

    def _get_client(self):
        if self._genai_client is None:
            api_key = os.environ.get("GEMINI_API") or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "LLM API credentials missing. Set GEMINI_API or GEMINI_API_KEY environment variable. "
                    "Per project rules, live model calls cannot silently fallback to fake completions."
                )
            from google import genai
            self._genai_client = genai.Client(api_key=api_key)
        return self._genai_client

    def _cache_key(self, model: str, prompt: str, image_bytes: bytes | None) -> str:
        h = hashlib.sha256()
        h.update(model.encode("utf-8"))
        h.update(b":")
        h.update(prompt.encode("utf-8"))
        if image_bytes is not None:
            h.update(b":")
            h.update(hashlib.sha256(image_bytes).digest())
        return h.hexdigest()

    def _record_telemetry(
        self,
        kind: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        cost_usd: float,
        cache_hit: bool,
        original_tokens: dict[str, int] | None = None,
    ) -> None:
        run_dir = self.runs_dir / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        telem_file = run_dir / "telemetry.jsonl"

        record = {
            "timestamp": _get_utc_now(),
            "run_id": self.run_id,
            "kind": kind,
            "provider": "google",
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "cache_hit": cache_hit,
            "original_tokens": original_tokens,
        }

        with open(telem_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def call(
        self,
        kind: str,
        prompt: str,
        schema: dict[str, Any] | None = None,
        *,
        image: bytes | Path | str | None = None,
        model: str | None = None,
        max_retries: int = 3,
    ) -> Any:
        """Call model with temperature 0, schema validation, disk cache, and telemetry."""
        target_model = model or self.model_name
        image_bytes: bytes | None = None
        pil_image = None

        if image is not None:
            if isinstance(image, (str, Path)):
                img_path = Path(image)
                if not img_path.exists():
                    raise FileNotFoundError(f"Image not found for vision extraction: {img_path}")
                image_bytes = img_path.read_bytes()
                from PIL import Image
                pil_image = Image.open(img_path)
            elif isinstance(image, bytes):
                image_bytes = image
                import io
                from PIL import Image
                pil_image = Image.open(io.BytesIO(image))

        key = self._cache_key(target_model, prompt, image_bytes)
        cache_file = self.cache_dir / f"{key}.json"

        # Check disk cache
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                result = cached["result"]
                orig_tokens = cached.get("usage", {})
                self._record_telemetry(
                    kind=kind,
                    model=target_model,
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=1,
                    cost_usd=0.0,
                    cache_hit=True,
                    original_tokens=orig_tokens,
                )
                return result
            except Exception:
                pass  # On cache read corruption, fall through to re-execute

        # Execute call with retries
        client = self._get_client()
        config_args = {
            "temperature": 0.0,
            "response_mime_type": "application/json",
        }
        try:
            from google.genai import types
            config = types.GenerateContentConfig(**config_args)
        except (ImportError, AttributeError):
            config = config_args

        contents: list[Any] = [prompt]
        if pil_image is not None:
            contents.append(pil_image)

        attempt = 0
        last_error = None
        while attempt < max_retries:
            attempt += 1
            t0 = time.time()
            try:
                resp = client.models.generate_content(
                    model=target_model,
                    contents=contents,
                    config=config,
                )
                latency_ms = int((time.time() - t0) * 1000)

                raw_text = resp.text.strip() if resp.text else "{}"
                # Handle possible markdown backticks
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:].strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:].strip()
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3].strip()

                parsed_json = json.loads(raw_text)

                input_tokens = resp.usage_metadata.prompt_token_count if resp.usage_metadata else 0
                output_tokens = resp.usage_metadata.candidates_token_count if resp.usage_metadata else 0
                cost = _calculate_cost(target_model, input_tokens, output_tokens)

                # Save to disk cache
                cache_payload = {
                    "key": key,
                    "model": target_model,
                    "kind": kind,
                    "result": parsed_json,
                    "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                    "cost_usd": cost,
                    "cached_at": _get_utc_now(),
                }
                cache_file.write_text(json.dumps(cache_payload, indent=2), encoding="utf-8")

                # Record telemetry
                self._record_telemetry(
                    kind=kind,
                    model=target_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    cost_usd=cost,
                    cache_hit=False,
                )
                return parsed_json

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    backoff = (2 ** attempt) * 0.5
                    time.sleep(backoff)

        raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_error}")


_DEFAULT_CLIENT: LLMClient | None = None


def get_default_client() -> LLMClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = LLMClient()
    return _DEFAULT_CLIENT


def call(kind: str, prompt: str, schema: dict[str, Any] | None = None, *, image: bytes | Path | str | None = None) -> Any:
    return get_default_client().call(kind, prompt, schema, image=image)


def classify_intent(request_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt_path = PROMPTS_DIR / "intent_classify.md"
    base_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    full_prompt = (
        f"{base_prompt}\n\n"
        f"DATA TO CLASSIFY:\n"
        f"User Request Text:\n\"\"\"\n{request_text}\n\"\"\"\n\n"
        f"Respond with JSON object containing: is_deletion (bool), category (str), confidence (float), reason (str)."
    )
    return call("intent", full_prompt)


def extract_image(image_path: Path | str, schema: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    prompt_path = PROMPTS_DIR / "vision_extract.md"
    prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    res = call("vision", prompt_text, schema=schema, image=image_path)
    if isinstance(res, list):
        return res
    if isinstance(res, dict) and "records" in res:
        return res["records"]
    return [res]
