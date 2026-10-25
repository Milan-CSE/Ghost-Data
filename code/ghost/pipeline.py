"""Audit Pipeline Orchestrator (code/ghost/pipeline.py).

Integrates Intent Classification, Identity Resolution, Ledger / Evidence Admissibility,
Ownership Linking, State Reconstruction, and Policy Compilation.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ghost.types import Case
from ghost.identity import load_identities, load_audit_log, build_bag
from ghost.ledger import Ledger
from ghost.ownership import OwnershipLinker
from ghost.state import StateReconstructor
from ghost.policy import PolicyCompiler, sort_steps
from ghost.intent import classify
from ghost.steps import finalize, to_json
from ghost.config import (
    USER_IDENTITIES_PATH,
    USER_AUDIT_LOG_PATH,
    SYSTEM_ACTIVITY_PATH,
    EVIDENCE_FILES_PATH,
    DATASET_DIR,
)


@dataclass
class AuditContext:
    """Pre-loaded global context for running deletion audit across cases."""
    identities: dict[str, Any]
    audit_log: list[dict[str, Any]]
    ledger: Ledger
    linker: OwnershipLinker
    state_recon: StateReconstructor
    compiler: PolicyCompiler

    @classmethod
    def load(cls, dataset_dir: Path | str = DATASET_DIR) -> AuditContext:
        ds = Path(dataset_dir)
        identities = load_identities(ds / "user_identities.csv")
        audit_log = load_audit_log(ds / "user_audit_log.csv")
        ledger = Ledger()
        ledger.ingest_manifest(ds / "evidence_files.csv", ds)
        linker = OwnershipLinker(ds / "system_activity.csv")
        state_recon = StateReconstructor()
        compiler = PolicyCompiler()
        return cls(
            identities=identities,
            audit_log=audit_log,
            ledger=ledger,
            linker=linker,
            state_recon=state_recon,
            compiler=compiler,
        )


def run_case(case: Case | dict[str, Any], ctx: AuditContext) -> tuple[str, str]:
    """Execute end-to-end deletion audit on a single request case.
    
    Returns:
        (deletion_status, steps_json_string)
    """
    # 1. Intent Classification
    intent = classify(case, ctx.linker._activities, use_llm=True)
    if intent.is_not_deletion:
        return "NOT_APPLICABLE", "[]"

    # 2. Identity Resolution
    bag = build_bag(case, ctx.identities, ctx.audit_log)

    # 3. Admissible Ledger View
    aud_at = case.audit_at if isinstance(case, Case) else case["audit_at"]
    view = ctx.ledger.admissible(aud_at)

    # 4. Ownership Linking
    owned_resources = ctx.linker.link(case, bag, view)

    # 5. State Reconstruction
    states = [ctx.state_recon.reconstruct(owned, view, case) for owned in owned_resources]

    # 6. Policy Compilation
    # Check if case has any non-compliant state / findings
    has_finding = any(ctx.compiler.has_finding(st) for st in states)
    is_complete = not has_finding
    status = "COMPLETE" if is_complete else "INCOMPLETE"

    # Compile steps for each resource
    all_steps = []
    for st in states:
        res_steps = ctx.compiler.compile_resource(st, is_case_complete=is_complete)
        all_steps.extend(res_steps)

    final_steps = finalize(all_steps)
    steps_json = to_json(final_steps)

    return status, steps_json
