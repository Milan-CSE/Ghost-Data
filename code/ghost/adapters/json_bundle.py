"""Adapter for JSON snapshot bundles (records_assurance_snapshot_bundle)."""
from __future__ import annotations
import hashlib
import json
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
            res_id = str(rec.get("resource_id") or "").strip(' \t\n\r"\'\\')
            if not res_id:
                continue

            em_set, hash_set, uid_set, ph_set = extract_identifiers_from_obj(rec)
            emails = set(em_set)
            hashes = set(hash_set)
            user_ids = set(uid_set)
            phones = set(ph_set)

            # Category & System
            system_id = normalize_system_id(res_id, data_store)
            category = infer_category(res_id, system_id, collection)
            state = State.PRESENT

            if category == "USER_PROFILE":
                if not emails and user_ids:
                    category = "ACCOUNT_TOMBSTONE"
                    state = State.REDACTED
                else:
                    status = str(rec.get("account_status", "")).upper()
                    if status in {"DELETED", "ABSENT", "CLOSED"}:
                        state = State.ABSENT
                    else:
                        state = State.PRESENT

            elif category == "ACCOUNT_TOMBSTONE":
                if not emails and not hashes and not phones:
                    state = State.REDACTED
                else:
                    state = State.PRESENT

            elif category == "ANALYTICS_PROFILE":
                if not emails and not user_ids and not hashes:
                    state = State.ANONYMIZED
                else:
                    state = State.PRESENT

            elif category in {"SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG"}:
                if not emails and not hashes and not phones and not user_ids:
                    state = State.REDACTED
                else:
                    state = State.PRESENT

            elif category == "BACKUP_ARCHIVE":
                restore_allowed = rec.get("restore_allowed")
                is_allowed = (
                    restore_allowed is True
                    or restore_allowed == 1
                    or str(restore_allowed).strip().lower() == "true"
                )
                state = State.ACTIVE if is_allowed else State.BLOCKED

            elif category == "DATA_FLOW":
                enabled = rec.get("enabled")
                is_active = (
                    enabled is True
                    or enabled == 1
                    or str(enabled).strip().lower() == "true"
                )
                state = State.ACTIVE if is_active else State.DISABLED

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
