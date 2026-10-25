"""Identity resolution and historical search surface reconstruction."""
from __future__ import annotations
import csv
import hashlib
from pathlib import Path
from typing import Any
from ghost.types import Case, IdentityBag
from ghost.config import USER_IDENTITIES_PATH, USER_AUDIT_LOG_PATH


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def load_identities(path: Path | str = USER_IDENTITIES_PATH) -> dict[str, dict[str, Any]]:
    """Load user_identities.csv as a dictionary indexed by user_id."""
    path = Path(path)
    identities: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            identities[row["user_id"]] = {
                "user_id": row["user_id"],
                "name": row.get("name", "").strip(),
                "email": row.get("email", "").strip(),
                "phone": row.get("phone", "").strip(),
                "email_hash": row.get("email_hash", "").strip() or _sha256(row.get("email", "")),
                "updated_at": row.get("updated_at", "").strip(),
            }
    return identities


def load_audit_log(path: Path | str = USER_AUDIT_LOG_PATH) -> list[dict[str, Any]]:
    """Load user_audit_log.csv."""
    path = Path(path)
    entries: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append({
                "audit_id": row["audit_id"],
                "user_id": row["user_id"],
                "event_time": row["event_time"].strip(),
                "field_name": row["field_name"].strip(),
                "old_value": row.get("old_value", "").strip(),
                "new_value": row.get("new_value", "").strip(),
            })
    return entries


def resolve_user_id(
    email: str,
    identities: dict[str, dict[str, Any]],
    audit_log: list[dict[str, Any]],
) -> str:
    """Resolve a case email (current or historical, case-insensitive) to a stable user_id."""
    target = email.strip().lower()

    # 1. Check current identities
    for uid, user in identities.items():
        if user["email"].strip().lower() == target:
            return uid

    # 2. Check historical emails in audit log
    for entry in audit_log:
        if entry["field_name"] == "email":
            if entry["old_value"].strip().lower() == target or entry["new_value"].strip().lower() == target:
                return entry["user_id"]

    raise ValueError(f"Could not resolve user_id for email: {email}")


def build_bag(
    case: Case | dict[str, Any],
    identities: dict[str, dict[str, Any]] | list[dict[str, Any]],
    audit_log: list[dict[str, Any]],
) -> IdentityBag:
    """Construct IdentityBag containing active identifiers at audit_at and the safe historical search surface."""
    # Normalize inputs
    if isinstance(case, dict):
        case_email = case["email"]
        case_audit_at = case["audit_at"]
    else:
        case_email = case.email
        case_audit_at = case.audit_at

    if isinstance(identities, list):
        identities_map = {u["user_id"]: u for u in identities}
    else:
        identities_map = identities

    user_id = resolve_user_id(case_email, identities_map, audit_log)
    user_snapshot = dict(identities_map[user_id])

    # Filter audit log for this user
    user_events = [e for e in audit_log if e["user_id"] == user_id]

    # Reconstruct point-in-time identity at audit_at by rolling back future events (event_time > audit_at)
    future_events = [e for e in user_events if e["event_time"] > case_audit_at]
    future_events.sort(key=lambda e: e["event_time"], reverse=True)

    reconstructed_state = {
        "email": user_snapshot.get("email", ""),
        "phone": user_snapshot.get("phone", ""),
        "name": user_snapshot.get("name", ""),
        "email_hash": user_snapshot.get("email_hash", "") or _sha256(user_snapshot.get("email", "")),
    }

    for fe in future_events:
        field = fe["field_name"]
        old_val = fe["old_value"]
        if field == "email":
            reconstructed_state["email"] = old_val
            reconstructed_state["email_hash"] = _sha256(old_val)
        elif field == "phone":
            reconstructed_state["phone"] = old_val
        elif field == "email_hash":
            reconstructed_state["email_hash"] = old_val

    active_at_audit = {
        "user_id": user_id,
        "email": reconstructed_state["email"],
        "phone": reconstructed_state["phone"],
        "email_hash": reconstructed_state["email_hash"],
        "name": reconstructed_state["name"],
    }

    # Construct search surface without leaking post-cutoff values
    surface: set[str] = set()
    surface.add(user_id)

    # Add active values at audit_at
    for k in ["email", "phone", "email_hash", "name"]:
        val = active_at_audit.get(k)
        if val:
            surface.add(val)
            if k == "email":
                surface.add(val.lower())
                surface.add(_sha256(val))
            elif k == "phone":
                norm_p = "".join(c for c in val if c.isdigit() or c == "+")
                if norm_p:
                    surface.add(norm_p)

    # Process audit entries:
    # 1. Historical entries (event_time <= audit_at): both old_value and new_value were active at or before cutoff
    # 2. Future entries (event_time > audit_at): only old_value was active before the transition;
    #    new_value is strictly EXCLUDED (anti-leakage)
    for entry in user_events:
        field = entry["field_name"]
        if entry["event_time"] <= case_audit_at:
            for val in [entry["old_value"], entry["new_value"]]:
                if val:
                    surface.add(val)
                    if field == "email":
                        surface.add(val.lower())
                        surface.add(_sha256(val))
                    elif field == "phone":
                        norm_p = "".join(c for c in val if c.isdigit() or c == "+")
                        if norm_p:
                            surface.add(norm_p)
        else:
            # Future event: old_value existed before this future transition, but new_value is post-cutoff
            old_val = entry["old_value"]
            if old_val:
                surface.add(old_val)
                if field == "email":
                    surface.add(old_val.lower())
                    surface.add(_sha256(old_val))
                elif field == "phone":
                    norm_p = "".join(c for c in old_val if c.isdigit() or c == "+")
                    if norm_p:
                        surface.add(norm_p)

    return IdentityBag(
        user_id=user_id,
        active_at_audit=active_at_audit,
        search_surface=frozenset(surface),
    )
