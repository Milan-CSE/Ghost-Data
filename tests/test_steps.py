"""Tests for canonical step ordering and serialization (ghost/steps.py)."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import pytest
from ghost.steps import (
    Step,
    sort_key,
    finalize,
    to_json,
    PHASE_RANK,
    OPERATION_ORDER,
    OPERATION_RANK,
    OP_PHASE_STATE,
)


def test_reproduce_all_32_samples():
    """Re-sorting all 32 sample arrays reproduces the canonical arrays exactly."""
    sample_path = Path(__file__).resolve().parent.parent / "dataset" / "sample_output.csv"
    assert sample_path.exists(), f"Sample output file missing: {sample_path}"

    with open(sample_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 32, f"Expected 32 sample rows, got {len(rows)}"

    for row in rows:
        case_id = row["case_id"]
        original_steps = json.loads(row["steps_json"])

        step_objs = [
            Step(
                phase=s["phase"],
                system_id=s["system_id"],
                resource_id=s["resource_id"],
                operation=s["operation"],
                state=s["state"],
                evidence_id=s.get("evidence_id", ""),
            )
            for s in original_steps
        ]

        finalized = finalize(step_objs)

        assert len(finalized) == len(original_steps), (
            f"{case_id}: step count mismatch ({len(finalized)} vs {len(original_steps)})"
        )

        for i, (orig, fin) in enumerate(zip(original_steps, finalized), 1):
            assert fin["step_no"] == i, f"{case_id}: step_no should be {i}"
            assert fin["phase"] == orig["phase"], f"{case_id} step {i}: phase mismatch"
            assert fin["system_id"] == orig["system_id"], f"{case_id} step {i}: system_id mismatch"
            assert fin["resource_id"] == orig["resource_id"], f"{case_id} step {i}: resource_id mismatch"
            assert fin["operation"] == orig["operation"], f"{case_id} step {i}: operation mismatch"
            assert fin["state"] == orig["state"], f"{case_id} step {i}: state mismatch"
            assert fin["evidence_id"] == orig["evidence_id"], f"{case_id} step {i}: evidence_id mismatch"


def test_phase_ordering():
    """Verify FINDING precedes REMEDIATION which precedes VERIFICATION."""
    s_verif = Step(
        phase="VERIFICATION",
        system_id="system_a",
        resource_id="res_01",
        operation="VERIFY_RECORD_ABSENT",
        state="ABSENT",
    )
    s_remed = Step(
        phase="REMEDIATION",
        system_id="system_a",
        resource_id="res_01",
        operation="DELETE_RECORD",
        state="ABSENT",
    )
    s_find = Step(
        phase="FINDING",
        system_id="system_a",
        resource_id="res_01",
        operation="REPORT_REMAINING_RECORD",
        state="PRESENT",
        evidence_id="ev_01",
    )

    # Input in reverse order: VERIFICATION, REMEDIATION, FINDING
    finalized = finalize([s_verif, s_remed, s_find])
    phases = [s["phase"] for s in finalized]
    assert phases == ["FINDING", "REMEDIATION", "VERIFICATION"]


def test_operation_ordering():
    """Verify operations follow the canonical OPERATION_ORDER within phases."""
    s1 = Step(
        phase="FINDING",
        system_id="system_a",
        resource_id="res_01",
        operation="REPORT_RESTORE_RISK",
        state="ACTIVE",
        evidence_id="ev_01",
    )
    s2 = Step(
        phase="FINDING",
        system_id="system_a",
        resource_id="res_01",
        operation="REPORT_REMAINING_RECORD",
        state="PRESENT",
        evidence_id="ev_02",
    )
    s3 = Step(
        phase="FINDING",
        system_id="system_a",
        resource_id="res_01",
        operation="REPORT_EXPOSED_PII",
        state="PRESENT",
        evidence_id="ev_03",
    )

    finalized = finalize([s1, s2, s3])
    ops = [s["operation"] for s in finalized]
    assert ops == ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_RESTORE_RISK"]


def test_tie_breaking_system_and_resource():
    """Verify tie-breaking by system_id then resource_id ascending."""
    s1 = Step(
        phase="FINDING",
        system_id="system_b",
        resource_id="res_01",
        operation="REPORT_REMAINING_RECORD",
        state="PRESENT",
        evidence_id="ev_01",
    )
    s2 = Step(
        phase="FINDING",
        system_id="system_a",
        resource_id="res_02",
        operation="REPORT_REMAINING_RECORD",
        state="PRESENT",
        evidence_id="ev_02",
    )
    s3 = Step(
        phase="FINDING",
        system_id="system_a",
        resource_id="res_01",
        operation="REPORT_REMAINING_RECORD",
        state="PRESENT",
        evidence_id="ev_03",
    )

    finalized = finalize([s1, s2, s3])
    ordered_pairs = [(s["system_id"], s["resource_id"]) for s in finalized]
    assert ordered_pairs == [("system_a", "res_01"), ("system_a", "res_02"), ("system_b", "res_01")]


def test_account_9_vs_account_10_ordering():
    """Verify standard string ordering applies to resource_ids ('account_10' < 'account_9')."""
    s_acc9 = Step(
        phase="VERIFICATION",
        system_id="account_service",
        resource_id="account_9",
        operation="VERIFY_RECORD_ABSENT",
        state="ABSENT",
        evidence_id="ev_01",
    )
    s_acc10 = Step(
        phase="VERIFICATION",
        system_id="account_service",
        resource_id="account_10",
        operation="VERIFY_RECORD_ABSENT",
        state="ABSENT",
        evidence_id="ev_02",
    )

    finalized = finalize([s_acc9, s_acc10])
    assert finalized[0]["resource_id"] == "account_10"
    assert finalized[1]["resource_id"] == "account_9"


def test_deduplication():
    """Verify duplicate steps with same (phase, system_id, resource_id, operation) are deduplicated."""
    s1 = Step(
        phase="FINDING",
        system_id="account_service",
        resource_id="account_001",
        operation="REPORT_REMAINING_RECORD",
        state="PRESENT",
        evidence_id="ev_01",
    )
    s2 = Step(
        phase="FINDING",
        system_id="account_service",
        resource_id="account_001",
        operation="REPORT_REMAINING_RECORD",
        state="PRESENT",
        evidence_id="ev_01",
    )

    finalized = finalize([s1, s2])
    assert len(finalized) == 1
    assert finalized[0]["step_no"] == 1


def test_consecutive_numbering_from_one():
    """Verify steps are numbered consecutively starting from 1."""
    steps = [
        Step("FINDING", "sys_1", "res_1", "REPORT_REMAINING_RECORD", "PRESENT", "ev_1"),
        Step("REMEDIATION", "sys_1", "res_1", "DELETE_RECORD", "ABSENT", ""),
        Step("VERIFICATION", "sys_1", "res_1", "VERIFY_RECORD_ABSENT", "ABSENT", ""),
    ]
    finalized = finalize(steps)
    step_nos = [s["step_no"] for s in finalized]
    assert step_nos == [1, 2, 3]


def test_to_json_compact():
    """Verify to_json produces valid compact JSON without extra whitespace."""
    steps = [
        {"step_no": 1, "phase": "FINDING", "system_id": "sys", "resource_id": "res", "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "ev"}
    ]
    json_str = to_json(steps)
    assert " " not in json_str
    parsed = json.loads(json_str)
    assert parsed == steps
