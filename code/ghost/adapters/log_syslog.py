"""Adapter for syslog formatted log files (log_syslog.py)."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from ghost.types import Fact, State

KV_PATTERN = re.compile(r'([a-zA-Z0-9_]+)=(?:"([^"]*)"|([^\s]+))')
SYSLOG_HEADER_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+<(\d+)>1\s+(\S+)\s+(\S+)"
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse syslog lines into Fact objects."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Syslog file not found: {path}")

    facts: list[Fact] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            header_match = SYSLOG_HEADER_PATTERN.match(line)
            line_time = header_match.group(1) if header_match else captured_at
            app_service = header_match.group(4) if header_match else ""

            # Extract key-value pairs from the rest of the line
            kv: dict[str, str] = {}
            for match in KV_PATTERN.finditer(line):
                k = match.group(1)
                v = match.group(2) if match.group(2) is not None else match.group(3)
                kv[k] = v

            res_id = kv.get("resource_id") or ""
            if not res_id:
                continue

            system_id = app_service or kv.get("service") or "account_service"
            event = kv.get("event", "")

            # Category
            if "attachment" in event or "attachment" in res_id or "file" in kv:
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

            for k in ["matched_value", "correlation_key", "lookup_key", "subject_key", "scan_key"]:
                val = kv.get(k)
                if val:
                    if "@" in val:
                        em = val.strip()
                        emails.add(em)
                        emails.add(em.lower())
                        hashes.add(_sha256(em))
                    elif val.startswith("user_"):
                        user_ids.add(val.strip())

            # State
            http_status = kv.get("http_status")
            rows = kv.get("rows")
            if http_status == "404" or rows == "0":
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
                    store="syslog",
                    covers_system=False,
                )
            )

    return facts
