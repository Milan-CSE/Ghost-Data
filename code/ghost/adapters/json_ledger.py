"""Adapter for JSON ledgers and service exports (json_ledger.py)."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from ghost.types import Fact, State


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse JSON ledgers, manifests, and service exports."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSON ledger file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    facts: list[Fact] = []

    # 1. Parse top-level 'records' list
    for rec in data.get("records", []):
        res_id = rec.get("resource_id") or ""
        if not res_id:
            continue

        system_id = rec.get("system") or rec.get("origin_system") or "account_service"
        category = rec.get("record_type") or "USER_PROFILE"
        rec_time = rec.get("recorded_at") or rec.get("captured_at") or captured_at

        emails: set[str] = set()
        hashes: set[str] = set()
        user_ids: set[str] = set()
        phones: set[str] = set()

        ref = rec.get("subject_reference") or rec.get("owner_email") or rec.get("customer_email") or ""
        if "@" in ref:
            emails.add(ref.strip())
            emails.add(ref.strip().lower())
            hashes.add(_sha256(ref))
        elif ref.startswith("user_"):
            user_ids.add(ref.strip())

        res_str = str(rec.get("result", "")).upper()
        if res_str in {"NOT_FOUND", "DELETED", "ABSENT"}:
            state = State.ABSENT
        elif res_str in {"ACTIVE", "ENABLED"}:
            state = State.ACTIVE
        elif res_str in {"DISABLED", "STOPPED"}:
            state = State.DISABLED
        elif res_str in {"BLOCKED"}:
            state = State.BLOCKED
        else:
            state = State.PRESENT

        facts.append(
            Fact(
                file_id=file_id,
                captured_at=rec_time,
                system_id=system_id,
                resource_id=res_id,
                category=category,
                state=state,
                emails=frozenset(emails),
                hashes=frozenset(hashes),
                user_ids=frozenset(user_ids),
                phones=frozenset(phones),
                store="records_ledger",
                covers_system=False,  # Targeted ledger records are observation-level
            )
        )

    # 2. Parse 'service_exports' dict
    service_exports = data.get("service_exports", {})
    for system_name, export_content in service_exports.items():
        if not isinstance(export_content, dict):
            continue

        for group_key, items in export_content.items():
            if not isinstance(items, list):
                continue

            for item in items:
                res_id = item.get("resource_id") or ""
                if not res_id:
                    continue

                item_time = item.get("observed_at") or captured_at
                emails = set()
                hashes = set()
                user_ids = set()
                phones = set()

                for k in ["customer_reference", "user_id", "subject_reference"]:
                    val = item.get(k)
                    if val:
                        user_ids.add(str(val).strip())

                for k in ["email", "customer_email", "owner_email", "requester_email"]:
                    val = item.get(k)
                    if val:
                        em = str(val).strip()
                        emails.add(em)
                        emails.add(em.lower())
                        hashes.add(_sha256(em))

                # Handle profile object in profile_lookups
                profile = item.get("profile")
                if isinstance(profile, dict):
                    if profile.get("email"):
                        em = str(profile["email"]).strip()
                        emails.add(em)
                        emails.add(em.lower())
                        hashes.add(_sha256(em))
                    if profile.get("customer_reference"):
                        user_ids.add(str(profile["customer_reference"]).strip())

                # State determination
                state = State.PRESENT
                category = "USER_PROFILE"

                if system_name == "account_service":
                    category = "USER_PROFILE"
                    status_code = item.get("status_code")
                    if status_code == 404 or profile is None:
                        state = State.ABSENT
                    else:
                        state = State.PRESENT

                elif system_name == "analytics_platform":
                    category = "ANALYTICS_PROFILE"
                    if not emails and not user_ids and not hashes:
                        state = State.ANONYMIZED
                    else:
                        state = State.PRESENT

                elif system_name == "backup_service":
                    category = "BACKUP_ARCHIVE"
                    allowed = item.get("restore_allowed")
                    is_allowed = allowed is True or str(allowed).strip().lower() == "true"
                    state = State.ACTIVE if is_allowed else State.BLOCKED

                elif system_name == "integration_service":
                    category = "INTEGRATION_DATA_FLOW"
                    enabled = item.get("enabled")
                    is_active = enabled is True or str(enabled).strip().lower() == "true"
                    state = State.ACTIVE if is_active else State.DISABLED

                elif system_name == "search_service":
                    category = "SEARCH_INDEX_ENTRY"
                    hits = item.get("hits", {})
                    if isinstance(hits, dict) and hits.get("total", 0) == 0:
                        state = State.ABSENT
                    else:
                        state = State.PRESENT

                elif system_name == "security_service":
                    category = "SECURITY_AUDIT_LOG"
                    state = State.PRESENT

                elif system_name == "support_platform":
                    category = "SUPPORT_MESSAGE"
                    state = State.PRESENT

                elif system_name == "export_service":
                    category = "USER_EXPORT"
                    state = State.PRESENT

                facts.append(
                    Fact(
                        file_id=file_id,
                        captured_at=item_time,
                        system_id=system_name,
                        resource_id=res_id,
                        category=category,
                        state=state,
                        emails=frozenset(emails),
                        hashes=frozenset(hashes),
                        user_ids=frozenset(user_ids),
                        phones=frozenset(phones),
                        store=f"service_export:{system_name}",
                        covers_system=False,
                    )
                )

    return facts
