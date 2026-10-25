"""Adapter for key-value formatted log files (log_kv.py)."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from ghost.types import (
    Fact,
    State,
    normalize_system_id,
    infer_category,
    extract_identifiers_from_obj,
)

KV_PATTERN = re.compile(r'([a-zA-Z0-9_]+)=(?:"([^"]*)"|([^\s]+))')
ISO_TIMESTAMP_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse key=value log lines into Fact objects, joining identifiers across trace_id."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    trace_emails: dict[str, set[str]] = {}
    trace_uids: dict[str, set[str]] = {}

    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            lines.append(line)

            kv: dict[str, str] = {}
            for match in KV_PATTERN.finditer(line):
                k = match.group(1)
                v = match.group(2) if match.group(2) is not None else match.group(3)
                kv[k] = v

            tr = kv.get("trace_id")
            if tr:
                em_set, hash_set, uid_set, ph_set = extract_identifiers_from_obj(kv)
                if em_set:
                    trace_emails.setdefault(tr, set()).update(em_set)
                if uid_set:
                    trace_uids.setdefault(tr, set()).update(uid_set)

    facts: list[Fact] = []
    for line in lines:
        ts_match = ISO_TIMESTAMP_PATTERN.match(line)
        line_time = ts_match.group(1) if ts_match else captured_at

        kv: dict[str, str] = {}
        for match in KV_PATTERN.finditer(line):
            k = match.group(1)
            v = match.group(2) if match.group(2) is not None else match.group(3)
            kv[k] = v

        res_id = kv.get("resource_id") or ""
        if not res_id:
            continue

        tr = kv.get("trace_id")
        raw_sys = kv.get("system") or kv.get("service") or ""
        system_id = normalize_system_id(res_id, raw_sys)
        category = infer_category(res_id, system_id, kv.get("record_type") or kv.get("event") or "")

        em_set, hash_set, uid_set, ph_set = extract_identifiers_from_obj(kv)
        emails = set(em_set)
        hashes = set(hash_set)
        user_ids = set(uid_set)
        phones = set(ph_set)

        if tr:
            if tr in trace_emails:
                emails.update(trace_emails[tr])
                for em in trace_emails[tr]:
                    hashes.add(_sha256(em))
            if tr in trace_uids:
                user_ids.update(trace_uids[tr])

        # Join trace-level identifiers
        if tr:
            if tr in trace_emails:
                for em in trace_emails[tr]:
                    emails.add(em)
                    emails.add(em.lower())
                    hashes.add(_sha256(em))
            if tr in trace_uids:
                user_ids.update(trace_uids[tr])

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
