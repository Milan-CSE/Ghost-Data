"""Deep inspect the 22 non-exact sample cases."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import csv
import json
from ghost.identity import load_identities, load_audit_log, build_bag
from ghost.ledger import Ledger
from ghost.ownership import OwnershipLinker
from ghost.state import StateReconstructor
from ghost.policy import PolicyCompiler, sort_steps

def inspect_cases():
    repo_root = Path(__file__).resolve().parent.parent
    dataset_dir = repo_root / "dataset"
    
    identities = load_identities(dataset_dir / "user_identities.csv")
    audit_log = load_audit_log(dataset_dir / "user_audit_log.csv")
    ledger = Ledger()
    ledger.ingest_manifest(dataset_dir / "evidence_files.csv", dataset_dir)
    linker = OwnershipLinker(dataset_dir / "system_activity.csv")
    state_recon = StateReconstructor()
    compiler = PolicyCompiler()

    with open(dataset_dir / "sample_deletion_requests.csv", "r", encoding="utf-8") as f:
        sample_requests = {r["case_id"]: r for r in csv.DictReader(f)}

    with open(dataset_dir / "sample_output.csv", "r", encoding="utf-8") as f:
        sample_truth = {r["case_id"]: r for r in csv.DictReader(f)}

    target_cases = [
        "case_03", "case_04", "case_07", "case_08", "case_09", "case_10",
        "case_12", "case_17", "case_18", "case_20", "case_21", "case_22",
        "case_23", "case_24", "case_25", "case_26", "case_27", "case_28",
        "case_29", "case_30", "case_31", "case_32"
    ]

    for cid in target_cases:
        req = sample_requests[cid]
        bag = build_bag(req, identities, audit_log)
        view = ledger.admissible(req["audit_at"])
        owned = linker.link(req, bag, view)
        states = [state_recon.reconstruct(o, view, req) for o in owned]
        truth_steps = json.loads(sample_truth[cid]["steps_json"])
        truth_status = sample_truth[cid]["deletion_status"]

        print(f"\n==========================================")
        print(f"CASE {cid}: requested={req['requested_at']}, reported={req['reported_at']}, audit={req['audit_at']}")
        print(f"User ID: {bag.user_id}, Active: {bag.active_at_audit}")
        print(f"Truth Status: {truth_status} ({len(truth_steps)} steps)")
        print(f"Truth Steps:")
        for s in truth_steps:
            print(f"  {s['phase']} | {s['system_id']} | {s['resource_id']} | {s['operation']} | {s['state']} | {s['evidence_id']}")
        print(f"Predicted Owned ({len(owned)}):")
        for o in owned:
            print(f"  {o.system_id}/{o.resource_id} ({o.category}) - signal={o.signal}")
        print(f"Predicted States ({len(states)}):")
        for st in states:
            print(f"  {st.system_id}/{st.resource_id} ({st.category}) -> {st.state.value} (ev={st.evidence_id})")

if __name__ == "__main__":
    inspect_cases()
