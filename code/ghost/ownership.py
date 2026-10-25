"""Ownership Linker (ownership.py).

Links resources to cases using grounded evidence, identity search surface,
and corroborating activity logs.
"""
from __future__ import annotations
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from ghost.types import Case, IdentityBag, OwnedResource, normalize_system_id, infer_category, VALID_SYSTEMS
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
                if norm_sys not in VALID_SYSTEMS:
                    continue
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
                if not (requested_at <= event_time <= audit_at):
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
                    res_id = (act.get("resource_id", "")).strip(' \t\n\r"\'\\')
                    if res_id:
                        norm_sys = normalize_system_id(res_id, raw_sys)
                        if norm_sys not in VALID_SYSTEMS:
                            continue
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

        # 3. Corroborating Activity Signals (Patch P6)
        # Activity alone must not establish primary ownership.
        # Check system_activity for deletion_worker events strictly within [requested_at, reported_at].
        if requested_at and reported_at:
            for key, cand in list(candidates.items()):
                corrobs = list(cand.corroborated_by)
                for act in self._activities:
                    res_id = (act.get("resource_id", "")).strip(' \t\n\r"\'\\')
                    if res_id == cand.resource_id:
                        event_time = act.get("event_time", "")
                        if requested_at <= event_time <= reported_at:
                            act_id = act.get("activity_id", "")
                            if act_id and act_id not in corrobs:
                                corrobs.append(act_id)
                if len(corrobs) > len(cand.corroborated_by):
                    candidates[key] = OwnedResource(
                        system_id=cand.system_id,
                        resource_id=cand.resource_id,
                        category=cand.category,
                        signal=cand.signal,
                        corroborated_by=tuple(corrobs),
                    )

        # 4. Refine resource category from deletion worker activity if available
        for (sys_id, res_id), cand in list(candidates.items()):
            worker_acts = [
                a for a in self._activities
                if (a.get("resource_id") or "").strip(' \t\n\r"\'\\') == res_id
                and "deletion_worker" in a.get("source_system", "")
                and a.get("event_time", "") <= audit_at
            ]
            if worker_acts:
                ev_type = worker_acts[-1].get("event_type")
                if sys_id == "support_platform":
                    if ev_type == "DELETE_RECORD":
                        candidates[(sys_id, res_id)] = OwnedResource(
                            system_id=cand.system_id,
                            resource_id=cand.resource_id,
                            category="SUPPORT_ATTACHMENT",
                            signal=cand.signal,
                            corroborated_by=cand.corroborated_by,
                        )
                    elif ev_type == "REDACT_RECORD":
                        candidates[(sys_id, res_id)] = OwnedResource(
                            system_id=cand.system_id,
                            resource_id=cand.resource_id,
                            category="SUPPORT_MESSAGE",
                            signal=cand.signal,
                            corroborated_by=cand.corroborated_by,
                        )
                elif sys_id == "analytics_platform":
                    if ev_type == "DELETE_RECORD":
                        candidates[(sys_id, res_id)] = OwnedResource(
                            system_id=cand.system_id,
                            resource_id=cand.resource_id,
                            category="MARKETING_PROFILE",
                            signal=cand.signal,
                            corroborated_by=cand.corroborated_by,
                        )
                    elif ev_type == "ANONYMIZE_RECORD":
                        candidates[(sys_id, res_id)] = OwnedResource(
                            system_id=cand.system_id,
                            resource_id=cand.resource_id,
                            category="ANALYTICS_PROFILE",
                            signal=cand.signal,
                            corroborated_by=cand.corroborated_by,
                        )

        # 5. Primary Account Profile Disambiguation:
        # If multiple account_service resources were grounded, prefer the one with activity corroboration
        account_keys = [k for k in candidates if k[0] == "account_service"]
        if len(account_keys) > 1:
            corrob_accs = [k for k in account_keys if candidates[k].corroborated_by]
            if len(corrob_accs) == 1:
                for k in account_keys:
                    if k not in corrob_accs:
                        del candidates[k]

        # Deterministic sorting: by system_id ascending, resource_id ascending
        sorted_resources = sorted(candidates.values(), key=lambda r: (r.system_id, r.resource_id))
        return sorted_resources
