"""Focused unit tests for PolicyCompiler (policy.py)."""
import pytest
from ghost.types import ResourceState, State
from ghost.policy import PolicyCompiler, sort_steps, POLICY_RULES
from ghost.steps import Step


def test_policy_all_15_rules_cardinality():
    """Verify exact policy action distribution and derived rule labelling."""
    delete_rules = [r for r in POLICY_RULES.values() if r.action == "DELETE"]
    redact_rules = [r for r in POLICY_RULES.values() if r.action == "REDACT"]
    anonymize_rules = [r for r in POLICY_RULES.values() if r.action == "ANONYMIZE"]
    retain_rules = [r for r in POLICY_RULES.values() if r.action == "RETAIN"]
    derived_rules = [r for r in POLICY_RULES.values() if r.status == "DERIVED_DESIGN_RULE"]

    assert len(delete_rules) == 7
    assert len(redact_rules) == 3
    assert len(anonymize_rules) == 2
    assert len(retain_rules) == 3
    assert len(derived_rules) == 6

    # Verify derived rules set
    derived_ids = {r.rule_id for r in derived_rules}
    assert derived_ids == {"rule_02", "rule_04", "rule_08", "rule_10", "rule_11", "rule_13"}


def test_policy_retained_records_invariant():
    """Retained records (SECURITY_AUDIT_LOG, LEGAL_HOLD_RECORD) emit ONLY VERIFY_RECORD_PRESENT."""
    compiler = PolicyCompiler()

    # Security audit log
    audit_st = ResourceState("security_service", "audit_1", "SECURITY_AUDIT_LOG", State.PRESENT, "ev_audit")
    steps = compiler.compile_resource(audit_st, is_case_complete=False)
    assert len(steps) == 1
    assert steps[0].phase == "VERIFICATION"
    assert steps[0].operation == "VERIFY_RECORD_PRESENT"
    assert steps[0].state == "PRESENT"

    # Legal hold record
    legal_st = ResourceState("legal_service", "legal_1", "LEGAL_HOLD_RECORD", State.PRESENT, "ev_legal")
    steps_legal = compiler.compile_resource(legal_st, is_case_complete=False)
    assert len(steps_legal) == 1
    assert steps_legal[0].phase == "VERIFICATION"
    assert steps_legal[0].operation == "VERIFY_RECORD_PRESENT"
    assert steps_legal[0].state == "PRESENT"


def test_policy_tombstone_clean_vs_dirty():
    """Test clean tombstone (REDACTED) vs dirty tombstone (PRESENT)."""
    compiler = PolicyCompiler()

    # Clean tombstone
    clean_st = ResourceState("identity_service", "tombstone_clean", "ACCOUNT_TOMBSTONE", State.REDACTED, "ev_tomb")
    clean_steps = compiler.compile_resource(clean_st, is_case_complete=True)
    assert len(clean_steps) == 1
    assert clean_steps[0].phase == "VERIFICATION"
    assert clean_steps[0].operation == "VERIFY_RECORD_REDACTED"
    assert clean_steps[0].state == "REDACTED"
    assert clean_steps[0].evidence_id == "ev_tomb"

    # Dirty tombstone (exposed PII)
    dirty_st = ResourceState("identity_service", "tombstone_dirty", "ACCOUNT_TOMBSTONE", State.PRESENT, "ev_tomb")
    dirty_steps = compiler.compile_resource(dirty_st, is_case_complete=False)
    assert len(dirty_steps) == 3
    assert dirty_steps[0].phase == "FINDING"
    assert dirty_steps[0].operation == "REPORT_EXPOSED_PII"
    assert dirty_steps[0].evidence_id == "ev_tomb"
    assert dirty_steps[1].phase == "REMEDIATION"
    assert dirty_steps[1].operation == "REDACT_RECORD"
    assert dirty_steps[1].evidence_id == ""
    assert dirty_steps[2].phase == "VERIFICATION"
    assert dirty_steps[2].operation == "VERIFY_RECORD_REDACTED"
    assert dirty_steps[2].evidence_id == ""


def test_policy_support_attachment_vs_message():
    """Test support attachment (DELETE) vs support message (REDACT)."""
    compiler = PolicyCompiler()

    # Attachment (DELETE)
    att_st = ResourceState("support_platform", "att_1", "SUPPORT_ATTACHMENT", State.PRESENT, "ev_sup")
    att_steps = compiler.compile_resource(att_st, is_case_complete=False)
    assert att_steps[0].operation == "REPORT_REMAINING_RECORD"
    assert att_steps[1].operation == "DELETE_RECORD"
    assert att_steps[2].operation == "VERIFY_RECORD_ABSENT"

    # Message (REDACT)
    msg_st = ResourceState("support_platform", "msg_1", "SUPPORT_MESSAGE", State.PRESENT, "ev_sup")
    msg_steps = compiler.compile_resource(msg_st, is_case_complete=False)
    assert msg_steps[0].operation == "REPORT_EXPOSED_PII"
    assert msg_steps[1].operation == "REDACT_RECORD"
    assert msg_steps[2].operation == "VERIFY_RECORD_REDACTED"


def test_policy_evidence_id_citation_contract():
    """For COMPLETE cases, all verifications cite evidence_id. For INCOMPLETE cases, remediations and verifications have empty evidence_id."""
    compiler = PolicyCompiler()
    account_st = ResourceState("account_service", "acc_1", "USER_PROFILE", State.ABSENT, "ev_snap")

    # Complete case
    complete_steps = compiler.compile_resource(account_st, is_case_complete=True)
    assert complete_steps[0].evidence_id == "ev_snap"

    # Incomplete case (already absent record verified post-remediation)
    incomplete_steps = compiler.compile_resource(account_st, is_case_complete=False)
    assert incomplete_steps[0].evidence_id == ""


def test_policy_macro_phase_and_intra_phase_sorting():
    """Verify sorting order: FINDING -> REMEDIATION -> VERIFICATION, with correct operation ranking."""
    steps = [
        Step("VERIFICATION", "account_service", "acc_1", "VERIFY_RECORD_ABSENT", "ABSENT"),
        Step("FINDING", "search_service", "srch_1", "REPORT_REMAINING_RECORD", "PRESENT", "ev_1"),
        Step("REMEDIATION", "search_service", "srch_1", "DELETE_RECORD", "ABSENT"),
        Step("FINDING", "support_platform", "msg_1", "REPORT_EXPOSED_PII", "PRESENT", "ev_2"),
        Step("REMEDIATION", "support_platform", "msg_1", "REDACT_RECORD", "REDACTED"),
        Step("VERIFICATION", "security_service", "aud_1", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ]
    sorted_dicts = sort_steps(steps)

    # Check phases order
    phases = [s["phase"] for s in sorted_dicts]
    assert phases == ["FINDING", "FINDING", "REMEDIATION", "REMEDIATION", "VERIFICATION", "VERIFICATION"]

    # Check consecutive 1-based numbering
    step_nos = [s["step_no"] for s in sorted_dicts]
    assert step_nos == [1, 2, 3, 4, 5, 6]

    # Check finding order: REPORT_REMAINING_RECORD (rank 10) before REPORT_EXPOSED_PII (rank 20)
    assert sorted_dicts[0]["operation"] == "REPORT_REMAINING_RECORD"
    assert sorted_dicts[1]["operation"] == "REPORT_EXPOSED_PII"
