import csv
import sys
sys.path.insert(0, "code")
from ghost.identity import load_identities, load_audit_log, build_bag

with open("dataset/deletion_requests.csv", "r", encoding="utf-8") as f:
    cases = {c["case_id"]: c for c in csv.DictReader(f)}

identities = load_identities("dataset/user_identities.csv")
audit = load_audit_log("dataset/user_audit_log.csv")

with open("dataset/system_activity.csv", "r", encoding="utf-8") as f:
    cls_events = [r for r in csv.DictReader(f) if r["event_type"] == "CLASSIFY_REQUEST"]

for i in range(533, 543):
    cid = f"case_{i}"
    c = cases[cid]
    bag = build_bag(c, identities, audit)
    print(f"\n{cid} | {c['email']} | user_id={bag.user_id if bag else None}")
    print(f"Request: {c['request_text']}")
    print(f"Intake window: [{c['requested_at']} .. {c['reported_at']}], audit_at: {c['audit_at']}")
    for ev in cls_events:
        if ev["event_time"] >= c["requested_at"] and ev["event_time"] <= min(c["reported_at"], c["audit_at"]):
            print(f"  Matched event: {ev['activity_id']} for {ev['resource_id']} at {ev['event_time']}: {ev['details']}")
