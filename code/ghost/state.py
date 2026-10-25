"""State Reconstruction (state.py).

Reconstructs the point-in-time state of each owned resource as of audit_at,
adhering to temporal boundaries, replica drift detection, coverage-based absence,
and deterministic fallbacks for unresolved states (Patch P3).
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from ghost.types import Case, OwnedResource, ResourceState, State
from ghost.ledger import View


def _record_unresolved_entry(case_id: str, system_id: str, resource_id: str, reason: str) -> None:
    """Record genuinely unresolved states in review/unresolved.md per Patch P3."""
    review_dir = Path("review")
    review_dir.mkdir(parents=True, exist_ok=True)
    unresolved_file = review_dir / "unresolved.md"
    entry = f"- Case `{case_id}`: Resource `{system_id}/{resource_id}` — {reason}\n"
    with open(unresolved_file, "a", encoding="utf-8") as f:
        f.write(entry)


class StateReconstructor:
    """Reconstructs resource state at audit_at from an admissible ledger View."""

    def reconstruct(
        self,
        owned: OwnedResource,
        view: View,
        case: Case | dict[str, Any],
    ) -> ResourceState:
        """Resolve the state and evidence citation for an OwnedResource at audit_at."""
        case_id = case["case_id"] if isinstance(case, dict) else case.case_id
        facts = view.all_for_resource(owned.system_id, owned.resource_id)

        # 1. Direct observations exist in admissible view
        if facts:
            # Sort chronologically
            facts.sort(key=lambda x: x.captured_at)
            latest_time = facts[-1].captured_at
            latest_facts = [f for f in facts if f.captured_at == latest_time]

            # Replica drift resolution: if multiple observations at latest timestamp,
            # prioritize surviving or active data (e.g. failover replica drift)
            selected_fact = latest_facts[-1]
            for f in latest_facts:
                if f.state in {State.PRESENT, State.ACTIVE}:
                    selected_fact = f
                    break

            # Handle process flow predicates (integration_service / backup_service)
            if owned.system_id == "integration_service":
                # Ensure state is process-compliant
                st = selected_fact.state
                if st not in {State.ACTIVE, State.DISABLED}:
                    st = State.ACTIVE if st == State.PRESENT else State.DISABLED
                return ResourceState(
                    system_id=owned.system_id,
                    resource_id=owned.resource_id,
                    category="DATA_FLOW",
                    state=st,
                    evidence_id=selected_fact.file_id,
                    is_unresolved=False,
                )

            if owned.system_id == "backup_service":
                st = selected_fact.state
                if st not in {State.ACTIVE, State.BLOCKED}:
                    st = State.ACTIVE if st == State.PRESENT else State.BLOCKED
                return ResourceState(
                    system_id=owned.system_id,
                    resource_id=owned.resource_id,
                    category="BACKUP_ARCHIVE",
                    state=st,
                    evidence_id=selected_fact.file_id,
                    is_unresolved=False,
                )

            # Security audit logs are always retained
            if owned.category == "SECURITY_AUDIT_LOG":
                return ResourceState(
                    system_id=owned.system_id,
                    resource_id=owned.resource_id,
                    category="SECURITY_AUDIT_LOG",
                    state=State.PRESENT,
                    evidence_id=selected_fact.file_id,
                    is_unresolved=False,
                )

            # Redacted records (Tombstones and Support Conversations)
            if owned.category in {"SUPPORT_MESSAGE", "ACCOUNT_TOMBSTONE"}:
                st = (
                    State.REDACTED
                    if (not selected_fact.emails and not selected_fact.phones and not selected_fact.hashes)
                    else State.PRESENT
                )
                return ResourceState(
                    system_id=owned.system_id,
                    resource_id=owned.resource_id,
                    category=owned.category,
                    state=st,
                    evidence_id=selected_fact.file_id,
                    is_unresolved=False,
                )

            # Standard entity resolution
            return ResourceState(
                system_id=owned.system_id,
                resource_id=owned.resource_id,
                category=owned.category,
                state=selected_fact.state,
                evidence_id=selected_fact.file_id,
                is_unresolved=False,
            )

        # 2. No direct observation of this resource exists in the admissible view
        # Absence vs. Non-Coverage: Check if an authoritative covering snapshot exists
        covering_file_id = view.covering_snapshot(owned.system_id)
        if covering_file_id:
            # Resource is verified ABSENT (or ANONYMIZED for analytics) via omission from authoritative covering store
            st = State.ANONYMIZED if owned.category == "ANALYTICS_PROFILE" else State.ABSENT
            return ResourceState(
                system_id=owned.system_id,
                resource_id=owned.resource_id,
                category=owned.category,
                state=st,
                evidence_id=covering_file_id,
                is_unresolved=False,
            )

        # 3. Patch P3 Fallback for Unresolved States:
        # If no covering store exists and no direct observation is available at cutoff,
        # record uncertainty in review/unresolved.md per Patch P3.
        # Fallback uses last admissible observation; never invent absence.
        reason = f"No direct observation or covering snapshot found in admissible view for {owned.system_id}"
        _record_unresolved_entry(case_id, owned.system_id, owned.resource_id, reason)

        fallback_state = State.ACTIVE if owned.category in {"DATA_FLOW", "BACKUP_ARCHIVE"} else State.PRESENT
        return ResourceState(
            system_id=owned.system_id,
            resource_id=owned.resource_id,
            category=owned.category,
            state=fallback_state,
            evidence_id="",
            is_unresolved=True,
            details=reason,
        )
