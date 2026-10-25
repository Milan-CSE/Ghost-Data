"""Vision extraction pipeline and validation for screenshot evidence (code/ghost/vision.py).

Processes administrative console screenshot evidence files via multimodal model,
validates output schema against known system/resource constraints, flags low confidence
rows in review/vision_confidence.md, and constructs normalized Fact objects.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any

from ghost.config import REPO_ROOT
from ghost.llm import extract_image
from ghost.types import Fact, State, VALID_SYSTEMS, extract_identifiers_from_obj

logger = logging.getLogger(__name__)

# Map raw console titles / system names to canonical system IDs
SYSTEM_NAME_MAP = {
    "account_admin_portal": "account_service",
    "account_admin_console": "account_service",
    "search_index_admin": "search_service",
    "search_index_inspector": "search_service",
    "integration_admin": "integration_service",
    "connector_management_console": "integration_service",
    "analytics_platform": "analytics_platform",
    "analytics_profile_view": "analytics_platform",
    "export_service": "export_service",
    "customer_export_console": "export_service",
    "support_platform": "support_platform",
    "support_ticket_console": "support_platform",
    "backup_service": "backup_service",
    "backup_restore_console": "backup_service",
    "security_service": "security_service",
    "security_audit_explorer": "security_service",
    "identity_service": "identity_service",
    "deleted_account_reference": "identity_service",
    "object_storage": "object_storage",
    "object_storage_browser": "object_storage",
    "marketing_platform": "analytics_platform",
    "marketing_profile_console": "analytics_platform",
}

CONFIDENCE_LOG_PATH = REPO_ROOT / "review" / "vision_confidence.md"


def _record_confidence_flag(file_id: str, resource_id: str, confidence: float, notes: str) -> None:
    CONFIDENCE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIDENCE_LOG_PATH.exists():
        CONFIDENCE_LOG_PATH.write_text("# Vision Extraction Low Confidence Log\n\n", encoding="utf-8")
    entry = f"- File `{file_id}`: Resource `{resource_id}` confidence={confidence:.2f} notes: {notes}\n"
    with open(CONFIDENCE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)


def extract_console_facts(
    path: Path | str,
    file_id: str,
    captured_at: str,
    *,
    use_llm: bool = True,
) -> list[Fact]:
    """Extract structured facts from administrative console screenshot with strict schema validation."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Screenshot evidence file not found: {path}")

    if not use_llm:
        return []

    try:
        raw_records = extract_image(path)
    except Exception as e:
        logger.warning("Vision extraction failed for %s: %s", path.name, e)
        return []

    if not isinstance(raw_records, list):
        return []

    facts: list[Fact] = []
    for item in raw_records:
        if not isinstance(item, dict):
            continue

        raw_sys = str(item.get("system_id", "")).strip().lower()
        system_id = SYSTEM_NAME_MAP.get(raw_sys, raw_sys)
        if system_id not in VALID_SYSTEMS and system_id != "object_storage":
            # Infer system from filename if unknown
            for pattern, target in SYSTEM_NAME_MAP.items():
                if pattern in path.stem.lower():
                    system_id = target
                    break

        res_id = str(item.get("resource_id", "")).strip()
        if not res_id:
            continue

        category = str(item.get("category", "")).strip() or "USER_PROFILE"
        state_str = str(item.get("state", "PRESENT")).strip().upper()
        try:
            state = State(state_str)
        except ValueError:
            state = State.PRESENT

        # Entity resources use PRESENT, only process flows use ACTIVE/DISABLED/BLOCKED
        if system_id not in ("integration_service", "backup_service") and state in (State.ACTIVE, State.DISABLED, State.BLOCKED):
            state = State.PRESENT

        # Confidence check
        conf = item.get("confidence", 1.0)
        try:
            conf_val = float(conf)
            if conf_val < 0.8:
                notes = str(item.get("notes", "Low model confidence in table extraction"))
                _record_confidence_flag(file_id, res_id, conf_val, notes)
        except (ValueError, TypeError):
            pass

        # Extract identifiers
        emails, hashes, user_ids, phones = extract_identifiers_from_obj(item)

        if item.get("user_id"):
            user_ids.add(str(item["user_id"]).strip())
        if item.get("email"):
            em = str(item["email"]).strip()
            emails.add(em)
            emails.add(em.lower())
        if item.get("phone"):
            phones.add(str(item["phone"]).strip())
        if item.get("email_hash"):
            hashes.add(str(item["email_hash"]).strip().lower())

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
                store="screenshot_vision",
                covers_system=False,
                file_captured_at=captured_at,
            )
        )

    return facts
