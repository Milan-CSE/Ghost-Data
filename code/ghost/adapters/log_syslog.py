"""Adapter for syslog formatted log files (log_syslog.py)."""
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
SYSLOG_HEADER_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+<(\d+)>1\s+(\S+)\s+(\S+)"
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse syslog lines into Fact objects, joining identifiers across trace_id."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Syslog file not found: {path}")

    # Pass 1: Collect identifiers associated with each trace_id
    trace_emails: dict[str, set[str]] = {}
    trace_uids: dict[str, set[str]] = {}

    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            lines.append(line)

            # Extract trace_id from header (e.g. token 5) or key-value
            tr = ""
            tokens = line.split()
            for tok in tokens[:6]:
                if tok.startswith("tr-") or tok.startswith("rb-"):
                    tr = tok
                    break

            kv: dict[str, str] = {}
            for match in KV_PATTERN.finditer(line):
                k = match.group(1)
                v = match.group(2) if match.group(2) is not None else match.group(3)
                kv[k] = v

            if not tr and kv.get("trace_id"):
                tr = kv["trace_id"]

            if tr:
                em_set, hash_set, uid_set, ph_set = extract_identifiers_from_obj(kv)
                if em_set:
                    trace_emails.setdefault(tr, set()).update(em_set)
                if uid_set:
                    trace_uids.setdefault(tr, set()).update(uid_set)

    facts: list[Fact] = []
    # Pass 2: Extract facts and join trace identifiers
    for line in lines:
        header_match = SYSLOG_HEADER_PATTERN.match(line)
        line_time = header_match.group(1) if header_match else captured_at
        app_service = header_match.group(4) if header_match else ""

        tr = ""
        tokens = line.split()
        for tok in tokens[:6]:
            if tok.startswith("tr-") or tok.startswith("rb-"):
                tr = tok
                break

        kv: dict[str, str] = {}
        for match in KV_PATTERN.finditer(line):
            k = match.group(1)
            v = match.group(2) if match.group(2) is not None else match.group(3)
            kv[k] = v

        if not tr and kv.get("trace_id"):
            tr = kv["trace_id"]

        ev = kv.get("event", "").lower()
        if ev.endswith("_started") or ev.endswith("_start"):
            continue

        res_id = (kv.get("resource_id") or "").strip(' \t\n\r"\'\\')
        if not res_id:
            continue

        raw_sys = app_service or kv.get("service") or ""
        system_id = normalize_system_id(res_id, raw_sys)
        category = infer_category(res_id, system_id, kv.get("event") or "")

        em_set, hash_set, uid_set, ph_set = extract_identifiers_from_obj(kv)
        emails = set(em_set)
        hashes = set(hash_set)
        user_ids = set(uid_set)
        phones = set(ph_set)

        # Join trace-level identifiers
        if tr:
            if tr in trace_emails:
                emails.update(trace_emails[tr])
                for em in trace_emails[tr]:
                    hashes.add(_sha256(em))
            if tr in trace_uids:
                user_ids.update(trace_uids[tr])

        # State
        http_status = kv.get("http_status")
        rows = kv.get("rows")
        if http_status == "404" or rows == "0":
            state = State.ABSENT
        elif (system_id == "analytics_platform" or category == "ANALYTICS_PROFILE") and not emails and not user_ids and not hashes:
            state = State.ANONYMIZED
        elif (system_id == "support_platform" or category in {"SUPPORT_MESSAGE", "ACCOUNT_TOMBSTONE"}) and not emails and not user_ids and not phones and not hashes:
            state = State.REDACTED
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
