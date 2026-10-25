"""Adapter for structured JSON Lines log files (log_jsonl.py)."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from ghost.types import (
    Fact,
    State,
    normalize_system_id,
    infer_category,
    extract_identifiers_from_obj,
)

ISO_TIMESTAMP_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse JSON Lines logs into Fact objects, joining identifiers across trace_id."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

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

            json_start = line.find("{")
            if json_start == -1:
                continue
            try:
                data = json.loads(line[json_start:])
            except Exception:
                continue

            tr = data.get("trace_id")
            if not tr:
                continue

            em_set, hash_set, uid_set, ph_set = extract_identifiers_from_obj(data)
            if em_set:
                trace_emails.setdefault(tr, set()).update(em_set)
            if uid_set:
                trace_uids.setdefault(tr, set()).update(uid_set)

    facts: list[Fact] = []
    # Pass 2: Extract facts and join trace identifiers
    for line in lines:
        ts_match = ISO_TIMESTAMP_PATTERN.match(line)
        line_time = ts_match.group(1) if ts_match else captured_at

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

        raw_sys = data.get("service") or data.get("logger") or ""
        system_id = normalize_system_id(res_id, raw_sys)
        event = data.get("event", "")
        category = infer_category(res_id, system_id, event)
        tr = data.get("trace_id")

        em_set, hash_set, uid_set, ph_set = extract_identifiers_from_obj(data)
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
