"""Adapter for structured JSON Lines log files (log_jsonl.py)."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from ghost.types import Fact, State

ISO_TIMESTAMP_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse JSON Lines logs into Fact objects."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    facts: list[Fact] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            ts_match = ISO_TIMESTAMP_PATTERN.match(line)
            line_time = ts_match.group(1) if ts_match else captured_at

            # Find the JSON part starting with '{'
            json_start = line.find("{")
            if json_start == -1:
                continue

            try:
                data = json.loads(line[json_start:])
            except Exception:
                continue

            res_id = data.get("resource_id") or ""
            if not res_id:
                continue

            system_id = data.get("service") or data.get("logger") or "account_service"
            event = data.get("event", "")

            # Category
            if "attachment" in event or "attachment" in res_id:
                category = "SUPPORT_ATTACHMENT"
            elif "message" in event or system_id == "support_platform":
                category = "SUPPORT_MESSAGE"
            elif system_id == "account_service":
                category = "USER_PROFILE"
            elif system_id == "search_service":
                category = "SEARCH_INDEX_ENTRY"
            elif system_id == "analytics_platform":
                category = "ANALYTICS_PROFILE"
            elif system_id == "security_service":
                category = "SECURITY_AUDIT_LOG"
            else:
                category = "USER_PROFILE"

            emails: set[str] = set()
            hashes: set[str] = set()
            user_ids: set[str] = set()
            phones: set[str] = set()

            for k in [
                "matched_value",
                "correlation_key",
                "lookup_key",
                "subject_key",
                "match_key",
                "subject_ref",
                "email",
            ]:
                val = data.get(k)
                if val:
                    val_str = str(val).strip()
                    if "@" in val_str:
                        emails.add(val_str)
                        emails.add(val_str.lower())
                        hashes.add(_sha256(val_str))
                    elif val_str.startswith("user_"):
                        user_ids.add(val_str)

            # State
            result = str(data.get("result", "")).lower()
            http_status = data.get("http_status")
            if http_status == 404 or result in {"miss", "not_found", "deleted"}:
                state = State.ABSENT
            else:
                state = State.PRESENT

            facts.append(
                Fact(
                    file_id=file_id,
                    captured_at=line_time,
                    system_id=system_id,
                    resource_id=res_id,
                    category=category,
                    state=state,
                    emails=frozenset(emails),
                    hashes=frozenset(hashes),
                    user_ids=frozenset(user_ids),
                    phones=frozenset(phones),
                    store="log_jsonl",
                    covers_system=False,
                )
            )

    return facts
