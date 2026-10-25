"""Adapter for key-value formatted log files (log_kv.py)."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from ghost.types import Fact, State

KV_PATTERN = re.compile(r'([a-zA-Z0-9_]+)=(?:"([^"]*)"|([^\s]+))')
ISO_TIMESTAMP_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse key=value log lines into Fact objects."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    facts: list[Fact] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Extract timestamp
            ts_match = ISO_TIMESTAMP_PATTERN.match(line)
            line_time = ts_match.group(1) if ts_match else captured_at

            # Extract key-value pairs
            kv: dict[str, str] = {}
            for match in KV_PATTERN.finditer(line):
                k = match.group(1)
                v = match.group(2) if match.group(2) is not None else match.group(3)
                kv[k] = v

            res_id = kv.get("resource_id") or ""
            if not res_id:
                continue

            system_id = kv.get("system") or kv.get("service") or "account_service"
            if system_id in {"readback_collector", "downstream_delivery_service", "log_router"}:
                system_id = kv.get("system") or "account_service"

            category = kv.get("record_type") or "USER_PROFILE"

            emails: set[str] = set()
            hashes: set[str] = set()
            user_ids: set[str] = set()
            phones: set[str] = set()

            for uid_k in ["customer_reference", "user_id", "subject_reference"]:
                val = kv.get(uid_k)
                if val and val != "null" and not val.startswith("+") and "@" not in val:
                    user_ids.add(val.strip())

            for email_k in ["email", "customer_email", "lookup_key", "subject_reference"]:
                val = kv.get(email_k)
                if val and "@" in val and val != "null":
                    em = val.strip()
                    emails.add(em)
                    emails.add(em.lower())
                    hashes.add(_sha256(em))

            for phone_k in ["phone"]:
                val = kv.get(phone_k)
                if val and val != "null":
                    phones.add(val.strip())

            # State mapping
            result = (kv.get("result") or kv.get("status") or "").upper()
            http_status = kv.get("http_status")
            rows = kv.get("rows")
            enabled = kv.get("enabled")
            restore_allowed = kv.get("restore_allowed")

            if http_status == "404" or rows == "0" or result in {"NOT_FOUND", "DELETED", "MISS"}:
                state = State.ABSENT
            elif enabled is not None:
                is_act = enabled.lower() == "true" or enabled == "1"
                state = State.ACTIVE if is_act else State.DISABLED
                category = "INTEGRATION_DATA_FLOW"
                system_id = "integration_service"
            elif restore_allowed is not None:
                is_res = restore_allowed.lower() == "true" or restore_allowed == "1"
                state = State.ACTIVE if is_res else State.BLOCKED
                category = "BACKUP_ARCHIVE"
                system_id = "backup_service"
            elif system_id == "analytics_platform" and not emails and not user_ids:
                state = State.ANONYMIZED
                category = "ANALYTICS_PROFILE"
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
                    store="log_kv",
                    covers_system=False,  # Logs are observation-only
                )
            )

    return facts
