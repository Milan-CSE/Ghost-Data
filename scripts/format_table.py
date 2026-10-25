"""Format the comparison table for non-exact sample cases."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path("code")))

import csv
import json
from ghost.identity import load_identities, load_audit_log, build_bag
from ghost.ledger import Ledger
from ghost.ownership import OwnershipLinker
from ghost.state import StateReconstructor
from ghost.policy import PolicyCompiler, sort_steps

dataset_dir = Path("dataset")
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

non_exact = []
for req in sample_requests:
    cid = req["case_id"]
    bag = build_bag(req, identities, audit_log)
    view = ledger.admissible(req["audit_at"])
    owned = linker.link(req, bag, view)
    states = [state_recon.reconstruct(o, view, req) for o in owned]
    has_finding = any(
        st.state.value == "PRESENT" if st.category not in {"BACKUP_ARCHIVE", "DATA_FLOW"}
        else st.state.value == "ACTIVE"
        for st in states
    )
    pred_status = "INCOMPLETE" if has_finding else "COMPLETE"
    raw_steps = []
    for st in states:
        raw_steps.extend(compiler.compile_resource(st, is_case_complete=(pred_status == "COMPLETE")))
    pred_steps = sort_steps(raw_steps)
    truth_steps = json.loads(sample_truth[cid]["steps_json"])
    truth_status = sample_truth[cid]["deletion_status"]

    if pred_steps != truth_steps or pred_status != truth_status:
        p_summary = "; ".join(f"{s['system_id']}/{s['resource_id']} ({s['operation']})" for s in pred_steps)
        t_summary = "; ".join(f"{s['system_id']}/{s['resource_id']} ({s['operation']})" for s in truth_steps)
        non_exact.append({
            "case_id": cid,
            "truth_status": truth_status,
            "pred_status": pred_status,
            "expected_steps": t_summary,
            "predicted_steps": p_summary,
            "truth_count": len(truth_steps),
            "pred_count": len(pred_steps),
        })

print(f"Total non-exact cases: {len(non_exact)}")
for item in non_exact:
    print(f"\n### {item['case_id']}")
    print(f"Expected ({item['truth_count']}): {item['expected_steps']}")
    print(f"Predicted ({item['pred_count']}): {item['predicted_steps']}")
