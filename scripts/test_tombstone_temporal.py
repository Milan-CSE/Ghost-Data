import sys
from pathlib import Path
sys.path.insert(0, "code")

import csv
from ghost.pipeline import AuditContext, run_case
from evaluation.score import score_predictions

ctx = AuditContext.load("dataset")

with open("dataset/sample_deletion_requests.csv", "r", encoding="utf-8") as f:
    sample_requests = list(csv.DictReader(f))

with open("dataset/sample_output.csv", "r", encoding="utf-8") as f:
    sample_truth = list(csv.DictReader(f))

# Test current behavior on samples
pred_rows = []
for req in sample_requests:
    cid = req["case_id"]
    status, steps_json = run_case(req, ctx)
    pred_rows.append({
        "case_id": cid,
        "deletion_status": status,
        "steps_json": steps_json
    })

res = score_predictions(pred_rows, sample_truth)
print(f"Sample Exact Match Rate: {res['row_exact_match_rate']:.2%}")
print(f"Sample Step Precision: {res['step_precision']:.2%}")
print(f"Sample Step Recall: {res['step_recall']:.2%}")
print(f"Sample Step F1: {res['step_f1']:.2%}")
print(f"Sample Error Counts: {res['error_taxonomy']}")
