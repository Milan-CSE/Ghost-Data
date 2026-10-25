"""Detailed case-by-case comparison against sample_output.csv."""
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

def run_detailed_analysis():
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

    results = []

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
                if st.state.value == "PRESENT":
                    has_finding = True
            elif cat in {'SUPPORT_MESSAGE', 'ACCOUNT_TOMBSTONE', 'EMAIL_DELIVERY_LOG'}:
                if st.state.value == "PRESENT":
                    has_finding = True
            elif cat in {'ANALYTICS_PROFILE', 'PRODUCT_TELEMETRY'}:
                if st.state.value == "PRESENT":
                    has_finding = True
            elif cat == 'BACKUP_ARCHIVE':
                if st.state.value == "ACTIVE":
                    has_finding = True
            elif cat == 'DATA_FLOW':
                if st.state.value == "ACTIVE":
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

        is_exact = (pred_status == truth_status and pred_dict_list == truth_dict_list)
        results.append({
            "case_id": case_id,
            "is_exact": is_exact,
            "pred_status": pred_status,
            "truth_status": truth_status,
            "pred_steps": pred_dict_list,
            "truth_steps": truth_dict_list,
            "owned_resources": owned_resources,
            "states": states,
        })

    exact_count = sum(1 for r in results if r["is_exact"])
    status_match_count = sum(1 for r in results if r["pred_status"] == r["truth_status"])
    print(f"Total: {len(results)} | Exact: {exact_count} | Status Match: {status_match_count}")
    
    non_exact = [r for r in results if not r["is_exact"]]
    print(f"Non-exact cases count: {len(non_exact)}")
    for r in non_exact:
        cid = r["case_id"]
        t_res = [(s["system_id"], s["resource_id"], s["operation"], s["state"], s["evidence_id"]) for s in r["truth_steps"]]
        p_res = [(s["system_id"], s["resource_id"], s["operation"], s["state"], s["evidence_id"]) for s in r["pred_steps"]]
        t_set = set(t_res)
        p_set = set(p_res)
        missing_in_pred = t_set - p_set
        extra_in_pred = p_set - t_set
        print(f"\n--- {cid} (Status P={r['pred_status']} vs T={r['truth_status']}) ---")
        if missing_in_pred:
            print(f"  Missing in pred ({len(missing_in_pred)}):")
            for m in missing_in_pred:
                print(f"    - {m}")
        if extra_in_pred:
            print(f"  Extra in pred ({len(extra_in_pred)}):")
            for e in extra_in_pred:
                print(f"    - {e}")

if __name__ == "__main__":
    run_detailed_analysis()
