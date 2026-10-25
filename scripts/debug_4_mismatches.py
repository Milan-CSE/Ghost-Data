import sys
from pathlib import Path
sys.path.insert(0, str(Path('code')))
sys.path.insert(0, '.')

from scripts.test_refined_pipeline import *

for cid in ['case_03', 'case_26', 'case_27', 'case_28']:
    req = [r for r in sample_requests if r['case_id'] == cid][0]
    audit_at = req['audit_at']
    view = ledger.admissible(audit_at)
    # find row in pred_rows
    p_row = [r for r in pred_rows if r['case_id'] == cid][0]
    t_row = [r for r in sample_truth if r['case_id'] == cid][0]
    print(f"\n=== {cid} ===")
    print("Truth:", json.loads(t_row['steps_json']))
    print("Pred:", json.loads(p_row['steps_json']))
