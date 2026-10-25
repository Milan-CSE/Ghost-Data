"""Analyze discrepancies between sample_output.csv and current pipeline predictions."""
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
from ghost.steps import finalize

def main():
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
        sample_requests = list(csv.DictReader(f))

    with open(dataset_dir / "sample_output.csv", "r", encoding="utf-8") as f:
        sample_truth = {r["case_id"]: r for r in csv.DictReader(f)}

    diff_cases = []

    for req in sample_requests:
        case_id = req["case_id"]
        bag = build_bag(req, identities, audit_log)
        view = ledger.admissible(req["audit_at"])
        owned_resources = linker.link(req, bag, view)
        states = [state_recon.reconstruct(owned, view, req) for owned in owned_resources]

        has_finding = False
        for st in states:
            cat = st.category
            if cat in {'USER_PROFILE', 'SEARCH_INDEX_ENTRY', 'SUPPORT_ATTACHMENT', 'USER_EXPORT', 'MARKETING_PROFILE', 'SECONDARY_IDENTIFIER', 'CACHE_ENTRY'}:
                if st.state == "PRESENT":
                    has_finding = True
            elif cat in {'SUPPORT_MESSAGE', 'ACCOUNT_TOMBSTONE', 'EMAIL_DELIVERY_LOG'}:
                if st.state == "PRESENT":
                    has_finding = True
            elif cat in {'ANALYTICS_PROFILE', 'PRODUCT_TELEMETRY'}:
                if st.state == "PRESENT":
                    has_finding = True
            elif cat == 'BACKUP_ARCHIVE':
                if st.state == "ACTIVE":
                    has_finding = True
            elif cat == 'DATA_FLOW':
                if st.state == "ACTIVE":
                    has_finding = True

        pred_status = "INCOMPLETE" if has_finding else "COMPLETE"
        is_complete = (pred_status == "COMPLETE")
        raw_steps = []
        for st in states:
            raw_steps.extend(compiler.compile_resource(st, is_case_complete=is_complete))

        final_steps = sort_steps(raw_steps)
        pred_dict_list = final_steps

        truth_row = sample_truth[case_id]
        truth_status = truth_row["deletion_status"]
        truth_dict_list = json.loads(truth_row["steps_json"])

        pred_json = json.dumps(pred_dict_list, separators=(",", ":"))
        truth_json = json.dumps(truth_dict_list, separators=(",", ":"))

        if pred_status != truth_status or pred_json != truth_json:
            diff_cases.append({
                "case_id": case_id,
                "email": req["email"],
                "audit_at": req["audit_at"],
                "pred_status": pred_status,
                "truth_status": truth_status,
                "pred_steps": pred_dict_list,
                "truth_steps": truth_dict_list,
                "owned_resources": [(o.system_id, o.resource_id, o.category, o.signal) for o in owned_resources],
                "states": [(s.system_id, s.resource_id, s.category, s.state.value, s.evidence_id) for s in states],
            })

    print(f"Total diff cases: {len(diff_cases)} / {len(sample_requests)}")
    for d in diff_cases:
        cid = d["case_id"]
        stat_match = "MATCH" if d["pred_status"] == d["truth_status"] else f"MISMATCH(P={d['pred_status']}, T={d['truth_status']})"
        print(f"\n=== Case: {cid} | Status: {stat_match} ===")
        print(f"  Truth steps ({len(d['truth_steps'])}):")
        for s in d["truth_steps"]:
            print(f"    - {s.get('phase')} {s.get('system_id')}/{s.get('resource_id')} op={s.get('operation')} st={s.get('state')} ev={s.get('evidence_id')}")
        print(f"  Pred steps ({len(d['pred_steps'])}):")
        for s in d["pred_steps"]:
            print(f"    - {s.get('phase')} {s.get('system_id')}/{s.get('resource_id')} op={s.get('operation')} st={s.get('state')} ev={s.get('evidence_id')}")
        print(f"  Owned resources: {d['owned_resources']}")

if __name__ == "__main__":
    main()
