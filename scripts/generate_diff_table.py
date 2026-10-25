"""Generate the detailed table of all non-exact sample cases."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path('code')))

import csv, json
from ghost.identity import load_identities, load_audit_log, build_bag
from ghost.ledger import Ledger
from ghost.ownership import OwnershipLinker
from ghost.state import StateReconstructor
from ghost.policy import PolicyCompiler, sort_steps

repo_root = Path('.')
dataset_dir = repo_root / 'dataset'

identities = load_identities(dataset_dir / 'user_identities.csv')
audit_log = load_audit_log(dataset_dir / 'user_audit_log.csv')
ledger = Ledger()
ledger.ingest_manifest(dataset_dir / 'evidence_files.csv', dataset_dir)
linker = OwnershipLinker(dataset_dir / 'system_activity.csv')
state_recon = StateReconstructor()
compiler = PolicyCompiler()

with open(dataset_dir / 'sample_deletion_requests.csv', 'r', encoding='utf-8') as f:
    sample_requests = list(csv.DictReader(f))

with open(dataset_dir / 'sample_output.csv', 'r', encoding='utf-8') as f:
    sample_truth = {r['case_id']: r for r in csv.DictReader(f)}

non_exact_table = []

for req in sample_requests:
    cid = req['case_id']
    bag = build_bag(req, identities, audit_log)
    view = ledger.admissible(req['audit_at'])
    owned = linker.link(req, bag, view)
    states = [state_recon.reconstruct(o, view, req) for o in owned]

    has_finding = any(
        (st.state.value == "PRESENT" and st.category in {
            'USER_PROFILE', 'SEARCH_INDEX_ENTRY', 'SUPPORT_ATTACHMENT', 'USER_EXPORT',
            'MARKETING_PROFILE', 'SECONDARY_IDENTIFIER', 'CACHE_ENTRY', 'SUPPORT_MESSAGE',
            'ACCOUNT_TOMBSTONE', 'EMAIL_DELIVERY_LOG', 'ANALYTICS_PROFILE', 'PRODUCT_TELEMETRY'
        }) or (st.state.value == "ACTIVE" and st.category in {'BACKUP_ARCHIVE', 'DATA_FLOW'})
        for st in states
    )

    pred_status = "INCOMPLETE" if has_finding else "COMPLETE"
    is_complete = (pred_status == "COMPLETE")
    raw_steps = []
    for st in states:
        raw_steps.extend(compiler.compile_resource(st, is_case_complete=is_complete))

    final_steps = sort_steps(raw_steps)
    truth_row = sample_truth[cid]
    truth_status = truth_row['deletion_status']
    truth_steps = json.loads(truth_row['steps_json'])

    is_exact = (pred_status == truth_status and final_steps == truth_steps)
    if not is_exact:
        non_exact_table.append({
            "case_id": cid,
            "pred_status": pred_status,
            "truth_status": truth_status,
            "pred_steps": final_steps,
            "truth_steps": truth_steps,
        })

print(f"Total non-exact cases: {len(non_exact_table)}")
for row in non_exact_table:
    cid = row['case_id']
    t_s = [(s['phase'], s['system_id'], s['resource_id'], s['operation'], s['state'], s['evidence_id']) for s in row['truth_steps']]
    p_s = [(s['phase'], s['system_id'], s['resource_id'], s['operation'], s['state'], s['evidence_id']) for s in row['pred_steps']]
    print(f"\nCase {cid}:")
    print(f"  Expected ({len(t_s)}): {t_s}")
    print(f"  Predicted ({len(p_s)}): {p_s}")
