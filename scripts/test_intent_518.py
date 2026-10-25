import csv
import sys
sys.path.insert(0, "code")

from ghost.intent import classify

with open("dataset/deletion_requests.csv", "r", encoding="utf-8") as f:
    cases = list(csv.DictReader(f))

with open("dataset/system_activity.csv", "r", encoding="utf-8") as f:
    activity = list(csv.DictReader(f))

not_app_cases = []
deletion_cases = []

for c in cases:
    res = classify(c, activity, use_llm=False)
    if res.is_not_deletion:
        not_app_cases.append((c["case_id"], res.tier, res.reason, c["request_text"]))
    else:
        deletion_cases.append(c["case_id"])

print(f"Total NOT_APPLICABLE: {len(not_app_cases)}")
print(f"Total DELETION: {len(deletion_cases)}")
print("\nNOT_APPLICABLE cases:")
for cid, tier, reason, txt in not_app_cases:
    print(f"- {cid} (Tier {tier}): {reason}\n  Text: {txt}\n")
