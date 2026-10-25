import csv
from datetime import datetime, timedelta

def parse_iso(ts):
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))

with open('dataset/sample_deletion_requests.csv', encoding='utf-8') as f:
    sample_requests = list(csv.DictReader(f))

with open('dataset/system_activity.csv', encoding='utf-8') as f:
    acts = list(csv.DictReader(f))

for req in sample_requests[:10]:
    cid = req['case_id']
    rep = req['reported_at']
    req_t = req['requested_at']
    if not rep or not req_t:
        continue
    dt_rep = parse_iso(rep)
    dt_req = parse_iso(req_t)
    matched = []
    for a in acts:
        if a.get('source_system') == 'deletion_worker':
            et = parse_iso(a['event_time'])
            # Check window around reported_at
            if dt_rep - timedelta(hours=2) <= et <= dt_rep + timedelta(minutes=15):
                matched.append(a)
    print(f"=== {cid} ({req_t} -> {rep}) ===")
    for m in matched:
        print(f"  {m['activity_id']} {m['event_time']} {m['target_system']:18} {m['resource_id']:15} {m['event_type']} {m['details'][:40]}")
