"""Canonical step ordering and serialization (verified against sample_output.csv)."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict

PHASE_RANK = {"FINDING": 1, "REMEDIATION": 2, "VERIFICATION": 3}
OPERATION_ORDER = [
    "REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK",
    "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD",
    "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
    "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED",
]
OPERATION_RANK = {op: i for i, op in enumerate(OPERATION_ORDER)}
OP_PHASE_STATE = {  # operation -> (phase, state), from the problem statement table
    "REPORT_REMAINING_RECORD": ("FINDING", "PRESENT"), "REPORT_EXPOSED_PII": ("FINDING", "PRESENT"),
    "REPORT_ACTIVE_DATA_FLOW": ("FINDING", "ACTIVE"), "REPORT_RESTORE_RISK": ("FINDING", "ACTIVE"),
    "DISABLE_DATA_FLOW": ("REMEDIATION", "DISABLED"), "BLOCK_RESTORE": ("REMEDIATION", "BLOCKED"),
    "DELETE_RECORD": ("REMEDIATION", "ABSENT"), "REDACT_RECORD": ("REMEDIATION", "REDACTED"),
    "ANONYMIZE_RECORD": ("REMEDIATION", "ANONYMIZED"),
    "VERIFY_RECORD_ABSENT": ("VERIFICATION", "ABSENT"), "VERIFY_RECORD_PRESENT": ("VERIFICATION", "PRESENT"),
    "VERIFY_RECORD_REDACTED": ("VERIFICATION", "REDACTED"),
    "VERIFY_RECORD_ANONYMIZED": ("VERIFICATION", "ANONYMIZED"),
    "VERIFY_DATA_FLOW_DISABLED": ("VERIFICATION", "DISABLED"), "VERIFY_RESTORE_BLOCKED": ("VERIFICATION", "BLOCKED"),
}

@dataclass(frozen=True)
class Step:
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str = ""

def sort_key(s: Step):
    return (PHASE_RANK[s.phase], OPERATION_RANK[s.operation], s.system_id, s.resource_id)

def finalize(steps: list[Step]) -> list[dict]:
    """Deduplicate, sort canonically, number from 1."""
    unique = {(s.phase, s.system_id, s.resource_id, s.operation): s for s in steps}.values()
    ordered = sorted(unique, key=sort_key)
    return [{"step_no": i, **asdict(s)} for i, s in enumerate(ordered, 1)]

def to_json(steps: list[dict]) -> str:
    return json.dumps(steps, separators=(",", ":"), ensure_ascii=False)
