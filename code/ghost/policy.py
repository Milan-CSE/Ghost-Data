"""Policy Compiler (policy.py).

Compiles observed resource states into compliant Finding, Remediation, and
Verification steps governed by deletion_rules.csv and AGENTS.md §6.4.
"""
from __future__ import annotations
from typing import NamedTuple
from ghost.types import ResourceState, State
from ghost.steps import Step, finalize, to_json


class RuleSpec(NamedTuple):
    rule_id: str
    category: str
    action: str  # "DELETE" | "REDACT" | "ANONYMIZE" | "RETAIN" | "PROCESS"
    status: str  # "VERIFIED_ON_SAMPLES" | "DERIVED_DESIGN_RULE"


# All 15 rules from deletion_rules.csv + operational DATA_FLOW
POLICY_RULES: dict[str, RuleSpec] = {
    "USER_PROFILE": RuleSpec("rule_01", "USER_PROFILE", "DELETE", "VERIFIED_ON_SAMPLES"),
    "SECONDARY_IDENTIFIER": RuleSpec("rule_02", "SECONDARY_IDENTIFIER", "DELETE", "DERIVED_DESIGN_RULE"),
    "SEARCH_INDEX_ENTRY": RuleSpec("rule_03", "SEARCH_INDEX_ENTRY", "DELETE", "VERIFIED_ON_SAMPLES"),
    "CACHE_ENTRY": RuleSpec("rule_04", "CACHE_ENTRY", "DELETE", "DERIVED_DESIGN_RULE"),
    "SUPPORT_MESSAGE": RuleSpec("rule_05", "SUPPORT_MESSAGE", "REDACT", "VERIFIED_ON_SAMPLES"),
    "SUPPORT_ATTACHMENT": RuleSpec("rule_06", "SUPPORT_ATTACHMENT", "DELETE", "VERIFIED_ON_SAMPLES"),
    "ANALYTICS_PROFILE": RuleSpec("rule_07", "ANALYTICS_PROFILE", "ANONYMIZE", "VERIFIED_ON_SAMPLES"),
    "PRODUCT_TELEMETRY": RuleSpec("rule_08", "PRODUCT_TELEMETRY", "ANONYMIZE", "DERIVED_DESIGN_RULE"),
    "USER_EXPORT": RuleSpec("rule_09", "USER_EXPORT", "DELETE", "VERIFIED_ON_SAMPLES"),
    "MARKETING_PROFILE": RuleSpec("rule_10", "MARKETING_PROFILE", "DELETE", "DERIVED_DESIGN_RULE"),
    "EMAIL_DELIVERY_LOG": RuleSpec("rule_11", "EMAIL_DELIVERY_LOG", "REDACT", "DERIVED_DESIGN_RULE"),
    "SECURITY_AUDIT_LOG": RuleSpec("rule_12", "SECURITY_AUDIT_LOG", "RETAIN", "VERIFIED_ON_SAMPLES"),
    "LEGAL_HOLD_RECORD": RuleSpec("rule_13", "LEGAL_HOLD_RECORD", "RETAIN", "DERIVED_DESIGN_RULE"),
    "BACKUP_ARCHIVE": RuleSpec("rule_14", "BACKUP_ARCHIVE", "RETAIN", "VERIFIED_ON_SAMPLES"),
    "ACCOUNT_TOMBSTONE": RuleSpec("rule_15", "ACCOUNT_TOMBSTONE", "REDACT", "VERIFIED_ON_SAMPLES"),
    "DATA_FLOW": RuleSpec("process_flow", "DATA_FLOW", "PROCESS", "VERIFIED_ON_SAMPLES"),
}


def sort_steps(steps: list[Step]) -> list[dict]:
    """Sort steps strictly according to macro phase and intra-phase hierarchy, returning dicts numbered from 1."""
    return finalize(steps)


class PolicyCompiler:
    """Compiles resource states into compliant Finding, Remediation, and Verification steps."""

    def compile_resource(
        self,
        res_state: ResourceState,
        is_case_complete: bool,
    ) -> list[Step]:
        """Generate findings, remediations, and verification steps for a single resource state."""
        category = res_state.category
        rule = POLICY_RULES.get(category, POLICY_RULES["USER_PROFILE"])
        action = rule.action
        curr_state = res_state.state
        evidence_id = res_state.evidence_id
        verification_evidence_id = evidence_id if is_case_complete else ""

        steps: list[Step] = []

        # 1. RETAINED Records (SECURITY_AUDIT_LOG, LEGAL_HOLD_RECORD)
        # Policy invariant: Always retained; never emit findings or deletion/redaction remediations!
        if action == "RETAIN" and category in {"SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"}:
            steps.append(
                Step(
                    phase="VERIFICATION",
                    system_id=res_state.system_id,
                    resource_id=res_state.resource_id,
                    operation="VERIFY_RECORD_PRESENT",
                    state="PRESENT",
                    evidence_id=verification_evidence_id,
                )
            )
            return steps

        # 2. BACKUP_ARCHIVE (rule_14)
        if category == "BACKUP_ARCHIVE":
            if curr_state == State.ACTIVE:
                # Restore risk exists
                steps.append(
                    Step(
                        phase="FINDING",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="REPORT_RESTORE_RISK",
                        state="ACTIVE",
                        evidence_id=evidence_id,
                    )
                )
                steps.append(
                    Step(
                        phase="REMEDIATION",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="BLOCK_RESTORE",
                        state="BLOCKED",
                        evidence_id="",
                    )
                )
            # Verification required for both compliant and remediated states
            steps.append(
                Step(
                    phase="VERIFICATION",
                    system_id=res_state.system_id,
                    resource_id=res_state.resource_id,
                    operation="VERIFY_RESTORE_BLOCKED",
                    state="BLOCKED",
                    evidence_id=verification_evidence_id,
                )
            )
            return steps

        # 3. Operational Process Flow (DATA_FLOW)
        if category == "DATA_FLOW":
            if curr_state == State.ACTIVE:
                # Active data flow can recreate data
                steps.append(
                    Step(
                        phase="FINDING",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="REPORT_ACTIVE_DATA_FLOW",
                        state="ACTIVE",
                        evidence_id=evidence_id,
                    )
                )
                steps.append(
                    Step(
                        phase="REMEDIATION",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="DISABLE_DATA_FLOW",
                        state="DISABLED",
                        evidence_id="",
                    )
                )
            steps.append(
                Step(
                    phase="VERIFICATION",
                    system_id=res_state.system_id,
                    resource_id=res_state.resource_id,
                    operation="VERIFY_DATA_FLOW_DISABLED",
                    state="DISABLED",
                    evidence_id=verification_evidence_id,
                )
            )
            return steps

        # 4. REDACT Rules (SUPPORT_MESSAGE, EMAIL_DELIVERY_LOG, ACCOUNT_TOMBSTONE)
        if action == "REDACT":
            if curr_state == State.PRESENT:
                # Exposed PII
                steps.append(
                    Step(
                        phase="FINDING",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="REPORT_EXPOSED_PII",
                        state="PRESENT",
                        evidence_id=evidence_id,
                    )
                )
                steps.append(
                    Step(
                        phase="REMEDIATION",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="REDACT_RECORD",
                        state="REDACTED",
                        evidence_id="",
                    )
                )
            steps.append(
                Step(
                    phase="VERIFICATION",
                    system_id=res_state.system_id,
                    resource_id=res_state.resource_id,
                    operation="VERIFY_RECORD_REDACTED",
                    state="REDACTED",
                    evidence_id=verification_evidence_id,
                )
            )
            return steps

        # 5. ANONYMIZE Rules (ANALYTICS_PROFILE, PRODUCT_TELEMETRY)
        if action == "ANONYMIZE":
            if curr_state == State.PRESENT:
                # Still attributable PII
                steps.append(
                    Step(
                        phase="FINDING",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="REPORT_EXPOSED_PII",
                        state="PRESENT",
                        evidence_id=evidence_id,
                    )
                )
                steps.append(
                    Step(
                        phase="REMEDIATION",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="ANONYMIZE_RECORD",
                        state="ANONYMIZED",
                        evidence_id="",
                    )
                )
            steps.append(
                Step(
                    phase="VERIFICATION",
                    system_id=res_state.system_id,
                    resource_id=res_state.resource_id,
                    operation="VERIFY_RECORD_ANONYMIZED",
                    state="ANONYMIZED",
                    evidence_id=verification_evidence_id,
                )
            )
            return steps

        # 6. DELETE Rules (USER_PROFILE, SECONDARY_IDENTIFIER, SEARCH_INDEX_ENTRY,
        #                   CACHE_ENTRY, SUPPORT_ATTACHMENT, USER_EXPORT, MARKETING_PROFILE)
        if action == "DELETE":
            if curr_state == State.PRESENT:
                # Remaining record
                steps.append(
                    Step(
                        phase="FINDING",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="REPORT_REMAINING_RECORD",
                        state="PRESENT",
                        evidence_id=evidence_id,
                    )
                )
                steps.append(
                    Step(
                        phase="REMEDIATION",
                        system_id=res_state.system_id,
                        resource_id=res_state.resource_id,
                        operation="DELETE_RECORD",
                        state="ABSENT",
                        evidence_id="",
                    )
                )
            steps.append(
                Step(
                    phase="VERIFICATION",
                    system_id=res_state.system_id,
                    resource_id=res_state.resource_id,
                    operation="VERIFY_RECORD_ABSENT",
                    state="ABSENT",
                    evidence_id=verification_evidence_id,
                )
            )
            return steps

        # Fallback default
        steps.append(
            Step(
                phase="VERIFICATION",
                system_id=res_state.system_id,
                resource_id=res_state.resource_id,
                operation="VERIFY_RECORD_ABSENT",
                state="ABSENT",
                evidence_id=verification_evidence_id,
            )
        )
        return steps
