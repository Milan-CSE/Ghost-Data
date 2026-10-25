import sys
from pathlib import Path
sys.path.insert(0, "code")

import csv, json
from ghost.pipeline import AuditContext, run_case
from evaluation.score import score_predictions

ctx = AuditContext.load("dataset")

with open("dataset/sample_deletion_requests.csv", "r", encoding="utf-8") as f:
    sample_requests = list(csv.DictReader(f))

with open("dataset/sample_output.csv", "r", encoding="utf-8") as f:
    sample_truth = list(csv.DictReader(f))

pred_rows = []
for req in sample_requests:
    cid = req["case_id"]
    status, steps_json = run_case(req, ctx)
    pred_rows.append({
        "case_id": cid,
        "deletion_status": status,
        "steps_json": steps_json
    })

results = score_predictions(pred_rows, sample_truth)
