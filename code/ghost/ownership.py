"""Ownership Linker (ownership.py).

Links resources to cases using grounded evidence, identity search surface,
and corroborating activity logs.
"""
from __future__ import annotations
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from ghost.types import Case, IdentityBag, OwnedResource, normalize_system_id, infer_category
from ghost.ledger import View
from ghost.config import SYSTEM_ACTIVITY_PATH


def _parse_iso(ts: str) -> datetime:
    """Parse ISO-8601 timestamp string to datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class OwnershipLinker:
    """Links platform resources to a case subject using grounded evidence and corroboration."""

    def __init__(self, activity_path: Path | str = SYSTEM_ACTIVITY_PATH):
        self.activity_path = Path(activity_path)
        self._activities: list[dict[str, str]] = []
        if self.activity_path.exists():
            with open(self.activity_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self._activities = list(reader)

    def link(
        self,
        case: Case | dict[str, Any],
        bag: IdentityBag,
        view: View,
    ) -> list[OwnedResource]:
        """Produce the sorted, deduplicated set of OwnedResources for this case."""
        if isinstance(case, dict):
            audit_at = case["audit_at"]
            requested_at = case.get("requested_at", "")
            reported_at = case.get("reported_at", "")
        else:
            audit_at = case.audit_at
            requested_at = case.requested_at
            reported_at = case.reported_at

        # Map (system_id, resource_id) -> OwnedResource
        candidates: dict[tuple[str, str], OwnedResource] = {}

        # 1. Primary Grounded Evidence Signals (view.by_identifier using search_surface)
        for ident in bag.search_surface:
            if not ident:
                continue
            matching_facts = view.by_identifier(ident)
            for fact in matching_facts:
                norm_sys = normalize_system_id(fact.resource_id, fact.system_id)
                category = fact.category or infer_category(fact.resource_id, norm_sys)
                key = (norm_sys, fact.resource_id)
                if key not in candidates:
                    candidates[key] = OwnedResource(
                        system_id=norm_sys,
                        resource_id=fact.resource_id,
                        category=category,
                        signal="identifier",
                        corroborated_by=(),
                    )

        # 2. Relational Signals from Activity Log (LINK_RESOURCE_IDENTITY)
        for act in self._activities:
            if act.get("event_type") == "LINK_RESOURCE_IDENTITY":
                event_time = act.get("event_time", "")
                if event_time > audit_at:
                    continue
                details = act.get("details", "")
                # Check if any strong identifier (length > 3) is present in details
                is_match = False
                for ident in bag.search_surface:
                    if len(ident) > 3 and ident.lower() in details.lower():
                        is_match = True
                        break
                if is_match:
                    raw_sys = act.get("target_system", "")
                    res_id = act.get("resource_id", "")
                    if res_id:
                        norm_sys = normalize_system_id(res_id, raw_sys)
                        category = infer_category(res_id, norm_sys)
                        key = (norm_sys, res_id)
                        act_id = act.get("activity_id", "")
                        corrob = (act_id,) if act_id else ()
                        if key in candidates:
                            # Augment existing candidate
                            existing = candidates[key]
                            candidates[key] = OwnedResource(
                                system_id=norm_sys,
                                resource_id=res_id,
                                category=existing.category,
                                signal="identifier",  # keep strongest signal
                                corroborated_by=existing.corroborated_by + corrob,
                            )
                        else:
                            candidates[key] = OwnedResource(
                                system_id=norm_sys,
                                resource_id=res_id,
                                category=category,
                                signal="relational",
                                corroborated_by=corrob,
                            )

        # 3. Corroborating Activity Signals for Account Profile (Patch P6)
        # When no account_service resource was grounded from evidence or relational links,
        # inspect deletion_worker events within [reported_at - 15 min, reported_at + 15 min].
        has_account = any(r.system_id == "account_service" for r in candidates.values())
        if not has_account and reported_at:
            try:
                rep_dt = _parse_iso(reported_at)
                w_start = rep_dt - timedelta(minutes=15)
                w_end = rep_dt + timedelta(minutes=15)

                account_acts = []
                for act in self._activities:
                    if act.get("source_system") == "deletion_worker" and act.get("target_system") == "account_service":
                        event_time = act.get("event_time", "")
                        if event_time > audit_at:
                            continue
                        act_dt = _parse_iso(event_time)
                        if w_start <= act_dt <= w_end:
                            account_acts.append(act)

                # Link if exactly one account was processed in this window
                if len(account_acts) == 1:
                    act = account_acts[0]
                    res_id = act.get("resource_id", "")
                    if res_id:
                        key = ("account_service", res_id)
                        act_id = act.get("activity_id", "")
                        candidates[key] = OwnedResource(
                            system_id="account_service",
                            resource_id=res_id,
                            category="USER_PROFILE",
                            signal="activity_corroboration",
                            corroborated_by=(act_id,) if act_id else (),
                        )
            except Exception:
                pass

        # Deterministic sorting: by system_id ascending, resource_id ascending
        sorted_resources = sorted(candidates.values(), key=lambda r: (r.system_id, r.resource_id))
        return sorted_resources
