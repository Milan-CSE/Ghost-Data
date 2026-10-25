import sys
from pathlib import Path
sys.path.insert(0, str(Path('code')))

import csv, json
from ghost.identity import load_identities, load_audit_log, build_bag
from ghost.ledger import Ledger
from ghost.ownership import OwnershipLinker
from ghost.state import StateReconstructor
from ghost.policy import PolicyCompiler, sort_steps

with open('dataset/evidence_files.csv', encoding='utf-8') as f:
    file_manifest_times = {r['file_id']: r['captured_at'] for r in csv.DictReader(f)}

identities = load_identities('dataset/user_identities.csv')
audit_log = load_audit_log('dataset/user_audit_log.csv')
ledger = Ledger()
ledger.ingest_manifest('dataset/evidence_files.csv', 'dataset')

with open('dataset/sample_deletion_requests.csv', encoding='utf-8') as f:
    sample_requests = list(csv.DictReader(f))

with open('dataset/sample_output.csv', encoding='utf-8') as f:
    sample_truth = {r['case_id']: r for r in csv.DictReader(f)}

print("Testing with file_manifest_time <= audit_at filter...")
# Filter ledger facts where file_manifest_times[f.file_id] <= audit_at
# and f.captured_at <= audit_at

for cid in ['case_09', 'case_23', 'case_24', 'case_26', 'case_27', 'case_28', 'case_29', 'case_30']:
    req = [r for r in sample_requests if r['case_id'] == cid][0]
    audit_at = req['audit_at']
    # Filter facts
    admissible_facts = [
        f for f in ledger._facts
        if f.captured_at <= audit_at and file_manifest_times[f.file_id] <= audit_at
    ]
    from ghost.ledger import View
    view = View(audit_at=audit_at, facts=admissible_facts)
    linker = OwnershipLinker('dataset/system_activity.csv')
    state_recon = StateReconstructor()
    bag = build_bag(req, identities, audit_log)
    owned = linker.link(req, bag, view)
    states = [state_recon.reconstruct(o, view, req) for o in owned]
    print(f"=== {cid} ===")
    print("Truth:", [(s['system_id'], s['resource_id'], s['operation'], s['state'], s['evidence_id']) for s in json.loads(sample_truth[cid]['steps_json'])])
    print("Pred States:", [(s.system_id, s.resource_id, s.category, s.state.value, s.evidence_id) for s in states])
