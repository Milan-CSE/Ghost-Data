"""Output invariants (verified to hold on all 32 sample answers)."""
from __future__ import annotations
import json
from .steps import OP_PHASE_STATE, PHASE_RANK, OPERATION_RANK

KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}

def check_row(case_id: str, status: str, steps_json: str) -> list[str]:
    errs: list[str] = []
    try:
        steps = json.loads(steps_json)
    except json.JSONDecodeError:
        return [f"{case_id}: steps_json is not valid JSON"]
    if status not in {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}:
        errs.append(f"{case_id}: bad status {status}")
    if status == "NOT_APPLICABLE":
        return errs + ([] if steps == [] else [f"{case_id}: NOT_APPLICABLE must have []"])
    last = (0, 0)
    for i, s in enumerate(steps, 1):
        if set(s) != KEYS: errs.append(f"{case_id}#{i}: wrong keys")
        if s.get("step_no") != i: errs.append(f"{case_id}#{i}: step_no")
        if OP_PHASE_STATE.get(s.get("operation")) != (s.get("phase"), s.get("state")):
            errs.append(f"{case_id}#{i}: operation/phase/state mismatch")
        phase = s.get("phase")
        op = s.get("operation")
        if phase in PHASE_RANK and op in OPERATION_RANK:
            key = (PHASE_RANK[phase], OPERATION_RANK[op])
            if key < last: errs.append(f"{case_id}#{i}: out of order")
            last = key
    phases = [s.get("phase") for s in steps]
    if status == "COMPLETE":
        if set(phases) - {"VERIFICATION"}: errs.append(f"{case_id}: COMPLETE has non-verification steps")
        if any(not s.get("evidence_id") for s in steps): errs.append(f"{case_id}: COMPLETE verification needs evidence_id")
    if status == "INCOMPLETE":
        if "FINDING" not in phases: errs.append(f"{case_id}: INCOMPLETE without finding")
        for s in steps:
            if s.get("phase") == "FINDING" and not s.get("evidence_id"): errs.append(f"{case_id}: finding without evidence")
            if s.get("phase") != "FINDING" and s.get("evidence_id"): errs.append(f"{case_id}: future step must use ''")
    return errs
