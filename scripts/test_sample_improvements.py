"""Test sample predictions using the actual code in code/ghost."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path('code')))

import csv, json
from ghost.identity import load_identities, load_audit_log, build_bag
from ghost.ledger import Ledger
from ghost.ownership import OwnershipLinker
from ghost.state import StateReconstructor
from ghost.policy import PolicyCompiler, sort_steps
from evaluation.score import score_predictions

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
    sample_truth = list(csv.DictReader(f))

pred_rows = []
unresolved_count = 0

for req in sample_requests:
    case_id = req['case_id']
    bag = build_bag(req, identities, audit_log)
    view = ledger.admissible(req['audit_at'])
    owned_resources = linker.link(req, bag, view)
    states = [state_recon.reconstruct(owned, view, req) for owned in owned_resources]

    for st in states:
        if st.is_unresolved:
            unresolved_count += 1

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
    pred_rows.append({
        "case_id": case_id,
        "deletion_status": pred_status,
        "steps_json": json.dumps(final_steps, separators=(',', ':')),
    })

print(f"Total fallback count on samples: {unresolved_count}")
metrics = score_predictions(pred_rows, sample_truth, verbose=True)
