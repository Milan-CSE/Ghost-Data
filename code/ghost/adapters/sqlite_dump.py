"""Adapter for SQLite dump exports (.sql)."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path
from ghost.types import Fact, State


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
            system_id = "account_service"
            category = "USER_PROFILE"
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
                if orig_system:
                    system_id = str(orig_system)

                if rec_json_str:
                    try:
                        rec = json.loads(rec_json_str)
                        for k in ["user_id", "customer_reference", "subject_reference"]:
                            if rec.get(k):
                                user_ids.add(str(rec[k]))
                        for k in ["email", "customer_email", "owner_email"]:
                            if rec.get(k):
                                em = str(rec[k]).strip()
                                emails.add(em)
                                emails.add(em.lower())
                                hashes.add(_sha256(em))
                        for k in ["phone", "owner_phone"]:
                            if rec.get(k):
                                phones.add(str(rec[k]).strip())
                        for k in ["email_hash"]:
                            if rec.get(k):
                                hashes.add(str(rec[k]).strip().lower())
                    except Exception:
                        pass

                if coll_name == "security_audit_events":
                    category = "SECURITY_AUDIT_LOG"
                elif coll_name == "customer_profiles":
                    category = "USER_PROFILE"
                elif coll_name == "search_documents":
                    category = "SEARCH_INDEX_ENTRY"
                elif coll_name == "analytics_profiles":
                    category = "ANALYTICS_PROFILE"
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
                category = "INTEGRATION_DATA_FLOW"
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
