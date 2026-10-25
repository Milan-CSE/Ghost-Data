"""Adapter for PNG vision extraction (png_vision.py).

Interface for parsing OCR and vision extractions from application screenshots.
Live model inference is deferred to Step 5; this adapter defines the deterministic
parsing contract and schema validation testable without API credentials.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
from ghost.types import Fact, State


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse_vision_payload(payload: list[dict[str, Any]], file_id: str, captured_at: str) -> list[Fact]:
    """Convert validated vision JSON extraction payload into Fact objects."""
    facts: list[Fact] = []
    for item in payload:
        res_id = item.get("resource_id") or ""
        if not res_id:
            continue

        system_id = item.get("system_id") or "account_service"
        category = item.get("category") or "USER_PROFILE"
        state_str = str(item.get("state", "PRESENT")).upper()

        try:
            state = State(state_str)
        except ValueError:
            state = State.PRESENT

        emails: set[str] = set()
        hashes: set[str] = set()
        user_ids: set[str] = set()
        phones: set[str] = set()

        if item.get("email"):
            em = str(item["email"]).strip()
            emails.add(em)
            emails.add(em.lower())
            hashes.add(_sha256(em))

        if item.get("user_id"):
            user_ids.add(str(item["user_id"]).strip())

        if item.get("phone"):
            phones.add(str(item["phone"]).strip())

        if item.get("email_hash"):
            hashes.add(str(item["email_hash"]).strip().lower())

        facts.append(
            Fact(
                file_id=file_id,
                captured_at=captured_at,
                system_id=system_id,
                resource_id=res_id,
                category=category,
                state=state,
                emails=frozenset(emails),
                hashes=frozenset(hashes),
                user_ids=frozenset(user_ids),
                phones=frozenset(phones),
                store="screenshot_vision",
                covers_system=False,
            )
        )
    return facts


def parse(
    path: Path | str,
    file_id: str,
    captured_at: str,
    vision_payload: list[dict[str, Any]] | None = None,
) -> list[Fact]:
    """Parse PNG screenshot.
    
    If vision_payload is supplied (or pre-cached), extracts structured facts.
    Otherwise returns empty list (live model extraction deferred to Step 5).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    if vision_payload is not None:
        return parse_vision_payload(vision_payload, file_id, captured_at)

    from ghost.vision import extract_console_facts
    return extract_console_facts(path, file_id, captured_at)
