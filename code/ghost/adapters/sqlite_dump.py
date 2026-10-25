"""Adapter for SQLite dump exports (.sql)."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path
from ghost.types import (
    Fact,
    State,
    normalize_system_id,
    infer_category,
    extract_identifiers_from_obj,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse a SQLite .sql dump file into normalized Fact objects."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")

    text = path.read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(text)
    except Exception as e:
        # Fallback for execution errors or partial SQL
        pass

    facts: list[Fact] = []
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        if r[0] != "snapshot_scope"
    ]

    for table in tables:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        col_idx = {name: idx for idx, name in enumerate(cols)}

        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        for row in rows:
            # Map columns to values
            def get_val(name: str):
                idx = col_idx.get(name)
                return row[idx] if idx is not None else None

            res_id = get_val("resource_id") or ""
            if not res_id:
                continue

            # Identify system and category
            emails: set[str] = set()
            hashes: set[str] = set()
            user_ids: set[str] = set()
            phones: set[str] = set()

            for uid_col in ["user_id", "customer_reference", "subject_reference"]:
                val = get_val(uid_col)
                if val:
                    user_ids.add(str(val))

            for email_col in ["email", "customer_email", "owner_email", "requester_email"]:
                val = get_val(email_col)
                if val:
                    em = str(val).strip()
                    emails.add(em)
                    emails.add(em.lower())
                    hashes.add(_sha256(em))

            for phone_col in ["phone", "owner_phone", "requester_phone"]:
                val = get_val(phone_col)
                if val:
                    phones.add(str(val).strip())

            for hash_col in ["email_hash"]:
                val = get_val(hash_col)
                if val:
                    hashes.add(str(val).strip().lower())

            # Default attributes
            system_id = normalize_system_id(res_id)
            category = infer_category(res_id, system_id, table)
            state = State.PRESENT

            # Table-specific logic
            if "customer_profiles" in table:
                system_id = "account_service"
                status = str(get_val("account_status") or "").upper()
                if not emails and user_ids:
                    category = "ACCOUNT_TOMBSTONE"
                    state = State.REDACTED
                elif status in {"DELETED", "ABSENT", "CLOSED"}:
                    state = State.ABSENT
                else:
                    category = "USER_PROFILE"
                    state = State.PRESENT

            elif "customer_data_" in table:
                # Generic table with record_json
                orig_system = get_val("origin_system")
                coll_name = get_val("collection_name")
                rec_json_str = get_val("record_json")
                rec: dict = {}

                if rec_json_str:
                    try:
                        rec = json.loads(rec_json_str)
                        em_set, hash_set, uid_set, ph_set = extract_identifiers_from_obj(rec)
                        emails.update(em_set)
                        hashes.update(hash_set)
                        user_ids.update(uid_set)
                        phones.update(ph_set)
                    except Exception:
                        pass

                system_id = normalize_system_id(res_id, orig_system or system_id)
                category = infer_category(res_id, system_id, coll_name)

                if category == "ANALYTICS_PROFILE":
                    if not emails and not user_ids and not hashes:
                        state = State.ANONYMIZED
                    else:
                        state = State.PRESENT
                elif category == "ACCOUNT_TOMBSTONE":
                    if not emails and not hashes and not phones:
                        state = State.REDACTED
                    else:
                        state = State.PRESENT
                elif category == "BACKUP_ARCHIVE":
                    restore_allowed = get_val("restore_allowed")
                    if restore_allowed is None and isinstance(rec, dict):
                        restore_allowed = rec.get("restore_allowed")
                    is_allowed = (
                        restore_allowed is True
                        or restore_allowed == 1
                        or str(restore_allowed).strip().lower() == "true"
                    )
                    state = State.ACTIVE if is_allowed else State.BLOCKED
                elif category == "DATA_FLOW":
                    enabled = get_val("enabled")
                    if enabled is None and isinstance(rec, dict):
                        enabled = rec.get("enabled")
                    is_active = (
                        enabled is True
                        or enabled == 1
                        or str(enabled).strip().lower() == "true"
                    )
                    state = State.ACTIVE if is_active else State.DISABLED
                elif category == "USER_PROFILE":
                    status = str(get_val("account_status") or (rec.get("account_status") if isinstance(rec, dict) else "")).upper()
                    if status in {"DELETED", "ABSENT", "CLOSED"}:
                        state = State.ABSENT
                    else:
                        state = State.PRESENT
                else:
                    state = State.PRESENT

            elif "search_documents" in table:
                system_id = "search_service"
                category = "SEARCH_INDEX_ENTRY"
                state = State.PRESENT

            elif "support_records" in table:
                system_id = "support_platform"
                category = "SUPPORT_MESSAGE"
                state = State.PRESENT

            elif "customer_exports" in table:
                system_id = "export_service"
                category = "USER_EXPORT"
                state = State.PRESENT

            elif "customer_analytics" in table:
                system_id = "analytics_platform"
                category = "ANALYTICS_PROFILE"
                if not emails and not user_ids and not hashes:
                    state = State.ANONYMIZED
                else:
                    state = State.PRESENT

            elif "connector_subscriptions" in table:
                system_id = "integration_service"
                category = "DATA_FLOW"
                enabled = get_val("enabled")
                is_active = (
                    enabled is True
                    or enabled == 1
                    or str(enabled).strip().lower() == "true"
                )
                state = State.ACTIVE if is_active else State.DISABLED

            elif "backup_restore_entries" in table:
                system_id = "backup_service"
                category = "BACKUP_ARCHIVE"
                restore_allowed = get_val("restore_allowed")
                is_allowed = (
                    restore_allowed is True
                    or restore_allowed == 1
                    or str(restore_allowed).strip().lower() == "true"
                )
                state = State.ACTIVE if is_allowed else State.BLOCKED

            elif "security_audit_records" in table:
                system_id = "security_service"
                category = "SECURITY_AUDIT_LOG"
                state = State.PRESENT

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
                    store=table,
                    covers_system=True,  # Full table dump is authoritative covering store
                )
            )

    conn.close()
    return facts
