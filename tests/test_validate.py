"""Tests for output invariants validator (ghost/validate.py)."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import pytest
from ghost.validate import check_row


def test_validate_all_32_samples():
    """All 32 sample answers must pass validation with 0 errors."""
    sample_path = Path(__file__).resolve().parent.parent / "dataset" / "sample_output.csv"
    assert sample_path.exists(), f"Sample output file missing: {sample_path}"

    with open(sample_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 32

    for row in rows:
        errs = check_row(row["case_id"], row["deletion_status"], row["steps_json"])
        assert errs == [], f"Validation failed for {row['case_id']}: {errs}"


def test_invalid_json():
    """Invalid JSON string must return decode error."""
    errs = check_row("case_001", "COMPLETE", "{bad json")
    assert any("not valid JSON" in e for e in errs)


def test_bad_status():
    """Unrecognized status must be rejected."""
    errs = check_row("case_001", "PENDING", "[]")
    assert any("bad status PENDING" in e for e in errs)


def test_not_applicable_contract():
    """NOT_APPLICABLE must have empty array; non-empty array must fail."""
    valid_errs = check_row("case_000", "NOT_APPLICABLE", "[]")
    assert valid_errs == []

    step = {
        "step_no": 1,
        "phase": "VERIFICATION",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
        "evidence_id": "ev_01",
    }
    invalid_errs = check_row("case_000", "NOT_APPLICABLE", json.dumps([step]))
    assert any("NOT_APPLICABLE must have []" in e for e in invalid_errs)


def test_step_wrong_keys():
    """Steps with missing or extra keys must fail validation."""
    # Missing 'evidence_id'
    bad_step1 = {
        "step_no": 1,
        "phase": "VERIFICATION",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
    }
    errs = check_row("case_001", "COMPLETE", json.dumps([bad_step1]))
    assert any("wrong keys" in e for e in errs)

    # Extra key 'extra_field'
    bad_step2 = {**bad_step1, "evidence_id": "ev_01", "extra_field": "bad"}
    errs = check_row("case_001", "COMPLETE", json.dumps([bad_step2]))
    assert any("wrong keys" in e for e in errs)


def test_step_no_sequence():
    """Steps with incorrect step_no must fail."""
    step = {
        "step_no": 5,  # Should be 1
        "phase": "VERIFICATION",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
        "evidence_id": "ev_01",
    }
    errs = check_row("case_001", "COMPLETE", json.dumps([step]))
    assert any("step_no" in e for e in errs)


def test_op_phase_state_mismatch():
    """Mismatched operation, phase, or state must fail."""
    step = {
        "step_no": 1,
        "phase": "FINDING",  # DELETE_RECORD belongs to REMEDIATION
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "DELETE_RECORD",
        "state": "ABSENT",
        "evidence_id": "ev_01",
    }
    errs = check_row("case_001", "INCOMPLETE", json.dumps([step]))
    assert any("operation/phase/state mismatch" in e for e in errs)


def test_steps_out_of_order():
    """Steps that violate phase or operation ranking must fail."""
    s1 = {
        "step_no": 1,
        "phase": "VERIFICATION",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
        "evidence_id": "ev_01",
    }
    s2 = {
        "step_no": 2,
        "phase": "FINDING",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "REPORT_REMAINING_RECORD",
        "state": "PRESENT",
        "evidence_id": "ev_02",
    }
    errs = check_row("case_001", "INCOMPLETE", json.dumps([s1, s2]))
    assert any("out of order" in e for e in errs)


def test_complete_status_constraints():
    """COMPLETE cases must have only VERIFICATION steps, all with non-empty evidence_id."""
    # COMPLETE with a FINDING step
    step_find = {
        "step_no": 1,
        "phase": "FINDING",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "REPORT_REMAINING_RECORD",
        "state": "PRESENT",
        "evidence_id": "ev_01",
    }
    errs1 = check_row("case_001", "COMPLETE", json.dumps([step_find]))
    assert any("COMPLETE has non-verification steps" in e for e in errs1)

    # COMPLETE with empty evidence_id
    step_empty_ev = {
        "step_no": 1,
        "phase": "VERIFICATION",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
        "evidence_id": "",
    }
    errs2 = check_row("case_001", "COMPLETE", json.dumps([step_empty_ev]))
    assert any("COMPLETE verification needs evidence_id" in e for e in errs2)


def test_incomplete_status_constraints():
    """INCOMPLETE cases must have >= 1 finding, findings need evidence, future steps need evidence_id == ''."""
    # INCOMPLETE without finding
    step_verif = {
        "step_no": 1,
        "phase": "VERIFICATION",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
        "evidence_id": "",
    }
    errs1 = check_row("case_001", "INCOMPLETE", json.dumps([step_verif]))
    assert any("INCOMPLETE without finding" in e for e in errs1)

    # INCOMPLETE finding without evidence_id
    step_finding_no_ev = {
        "step_no": 1,
        "phase": "FINDING",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "REPORT_REMAINING_RECORD",
        "state": "PRESENT",
        "evidence_id": "",
    }
    errs2 = check_row("case_001", "INCOMPLETE", json.dumps([step_finding_no_ev]))
    assert any("finding without evidence" in e for e in errs2)

    # INCOMPLETE future step with non-empty evidence_id
    step_find_ok = {
        "step_no": 1,
        "phase": "FINDING",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "REPORT_REMAINING_RECORD",
        "state": "PRESENT",
        "evidence_id": "ev_01",
    }
    step_remed_with_ev = {
        "step_no": 2,
        "phase": "REMEDIATION",
        "system_id": "account_service",
        "resource_id": "account_001",
        "operation": "DELETE_RECORD",
        "state": "ABSENT",
        "evidence_id": "ev_02",  # Should be empty string ""
    }
    errs3 = check_row("case_001", "INCOMPLETE", json.dumps([step_find_ok, step_remed_with_ev]))
    assert any("future step must use ''" in e for e in errs3)
