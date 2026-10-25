"""Adapter for shift handover text tables (handover_txt.py)."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from ghost.types import Fact, State

HANDOVER_ROW_PATTERN = re.compile(
    r"^-\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*(.*)$"
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse customer account handover text files."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Handover text file not found: {path}")

    facts: list[Fact] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            match = HANDOVER_ROW_PATTERN.match(line)
            if not match:
                continue

            time_str = match.group(1).strip()
            sys_id = match.group(2).strip()
            res_id = match.group(3).strip()
            cat = match.group(4).strip()
            res_state = match.group(5).strip().upper()
            ident = match.group(6).strip()

            emails: set[str] = set()
            hashes: set[str] = set()
            user_ids: set[str] = set()
            phones: set[str] = set()

            if "@" in ident:
                emails.add(ident)
                emails.add(ident.lower())
                hashes.add(_sha256(ident))
            elif ident.startswith("user_"):
                user_ids.add(ident)
            elif ident.startswith("+"):
                phones.add(ident)

            # Map state
            if res_state in {"NOT_FOUND", "DELETED", "ABSENT"}:
                state = State.ABSENT
            elif res_state in {"FOUND", "PRESENT"}:
                state = State.PRESENT
            elif res_state in {"ACTIVE", "ENABLED"}:
                state = State.ACTIVE
            elif res_state in {"DISABLED", "STOPPED"}:
                state = State.DISABLED
            elif res_state in {"BLOCKED"}:
                state = State.BLOCKED
            elif res_state in {"REDACTED"}:
                state = State.REDACTED
            elif res_state in {"ANONYMIZED"}:
                state = State.ANONYMIZED
            else:
                state = State.PRESENT

            facts.append(
                Fact(
                    file_id=file_id,
                    captured_at=time_str or captured_at,
                    system_id=sys_id,
                    resource_id=res_id,
                    category=cat,
                    state=state,
                    emails=frozenset(emails),
                    hashes=frozenset(hashes),
                    user_ids=frozenset(user_ids),
                    phones=frozenset(phones),
                    store="handover_table",
                    covers_system=False,  # Handover list is observation-level checks
                )
            )

    return facts
