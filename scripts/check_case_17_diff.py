import sys
from pathlib import Path
sys.path.insert(0, "code")

import csv
from ghost.pipeline import AuditContext, run_case
from evaluation.score import score_predictions

ctx = AuditContext.load("dataset")

# Let's inspect case_17 specifically
with open("dataset/sample_deletion_requests.csv", "r", encoding="utf-8") as f:
    sample_requests = {r["case_id"]: r for r in csv.DictReader(f)}

with open("dataset/sample_output.csv", "r", encoding="utf-8") as f:
    sample_truth = {r["case_id"]: r for r in csv.DictReader(f)}

c17_req = sample_requests["case_17"]
status, steps_json = run_case(c17_req, ctx)
print("case_17 current predicted steps:")
print(steps_json)
print("\ncase_17 ground truth steps:")
print(sample_truth["case_17"]["steps_json"])
