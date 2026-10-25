"""Adapter for JSON snapshot bundles (records_assurance_snapshot_bundle)."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from ghost.types import Fact, State


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse a JSON snapshot bundle.
    
    Evaluates each inner snapshot's captured_at independently of container exported_at.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSON bundle file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    snapshots = data.get("snapshots", [])
    facts: list[Fact] = []

    for snap in snapshots:
        # Use inner snapshot's captured_at if present; fallback to container captured_at
        snap_captured_at = snap.get("captured_at") or captured_at
        data_store = snap.get("data_store", "account_service")
        collection = snap.get("collection", "")
        records = snap.get("records", [])

        for rec in records:
            res_id = rec.get("resource_id") or ""
            if not res_id:
                continue

            emails: set[str] = set()
            hashes: set[str] = set()
            user_ids: set[str] = set()
            phones: set[str] = set()

            for uid_k in ["user_id", "customer_reference", "subject_reference"]:
                val = rec.get(uid_k)
                if val:
                    user_ids.add(str(val).strip())

            for email_k in ["email", "customer_email", "owner_email"]:
                val = rec.get(email_k)
                if val:
                    em = str(val).strip()
                    emails.add(em)
                    emails.add(em.lower())
                    hashes.add(_sha256(em))

            for phone_k in ["phone", "owner_phone"]:
                val = rec.get(phone_k)
                if val:
                    phones.add(str(val).strip())

            for hash_k in ["email_hash"]:
                val = rec.get(hash_k)
                if val:
                    hashes.add(str(val).strip().lower())

            # Category & State
            category = "USER_PROFILE"
            state = State.PRESENT

            if data_store == "account_service":
                if not emails and user_ids:
                    category = "ACCOUNT_TOMBSTONE"
                    state = State.REDACTED
                else:
                    category = "USER_PROFILE"
                    status = str(rec.get("account_status", "")).upper()
                    if status in {"DELETED", "ABSENT", "CLOSED"}:
                        state = State.ABSENT
                    else:
                        state = State.PRESENT

            elif data_store == "analytics_platform":
                category = "ANALYTICS_PROFILE"
                if not emails and not user_ids and not hashes:
                    state = State.ANONYMIZED
                else:
                    state = State.PRESENT

            elif data_store == "backup_service":
                category = "BACKUP_ARCHIVE"
                restore_allowed = rec.get("restore_allowed")
                is_allowed = (
                    restore_allowed is True
                    or restore_allowed == 1
                    or str(restore_allowed).strip().lower() == "true"
                )
                state = State.ACTIVE if is_allowed else State.BLOCKED

            elif data_store == "integration_service":
                category = "INTEGRATION_DATA_FLOW"
                enabled = rec.get("enabled")
                is_active = (
                    enabled is True
                    or enabled == 1
                    or str(enabled).strip().lower() == "true"
                )
                state = State.ACTIVE if is_active else State.DISABLED

            elif data_store == "search_service":
                category = "SEARCH_INDEX_ENTRY"
                state = State.PRESENT

            elif data_store == "security_service":
                category = "SECURITY_AUDIT_LOG"
                state = State.PRESENT

            elif data_store == "support_platform":
                category = "SUPPORT_MESSAGE"
                state = State.PRESENT

            elif data_store == "export_service":
                category = "USER_EXPORT"
                state = State.PRESENT

            facts.append(
                Fact(
                    file_id=file_id,
                    captured_at=snap_captured_at,
                    system_id=data_store,
                    resource_id=res_id,
                    category=category,
                    state=state,
                    emails=frozenset(emails),
                    hashes=frozenset(hashes),
                    user_ids=frozenset(user_ids),
                    phones=frozenset(phones),
                    store=f"{data_store}:{collection}",
                    covers_system=True,  # Snapshot bundles are authoritative full-collection snapshots
                )
            )

    return facts
