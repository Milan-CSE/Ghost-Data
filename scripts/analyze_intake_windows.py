import csv
from collections import defaultdict
from datetime import datetime, timedelta

def parse_iso(ts):
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))

with open('dataset/sample_deletion_requests.csv', encoding='utf-8') as f:
    sample_requests = list(csv.DictReader(f))

with open('dataset/sample_output.csv', encoding='utf-8') as f:
    sample_truth = {r['case_id']: r for r in csv.DictReader(f)}

with open('dataset/system_activity.csv', encoding='utf-8') as f:
    acts = list(csv.DictReader(f))

worker_acts = [a for a in acts if a.get('source_system') == 'deletion_worker']
print(f"Total deletion worker activities: {len(worker_acts)}")

# Group requests by reported_at
req_by_rep = defaultdict(list)
for req in sample_requests:
    rep = req.get('reported_at')
    if rep:
        req_by_rep[rep].append(req)

for rep, reqs in req_by_rep.items():
    dt_rep = parse_iso(rep)
    # acts in window [dt_rep - 2 hours, dt_rep + 15 min]
    win_acts = [
        a for a in worker_acts
        if dt_rep - timedelta(hours=2) <= parse_iso(a['event_time']) <= dt_rep + timedelta(minutes=15)
    ]
    print(f"\nReported At: {rep} ({len(reqs)} requests, {len(win_acts)} worker activities)")
    for r in reqs:
        cid = r['case_id']
        em = r['email']
        import json
        t_steps = json.loads(sample_truth[cid]['steps_json'])
        t_res = [(s['system_id'], s['resource_id'], s['operation']) for s in t_steps]
        print(f"  Req: {cid} ({em}) -> {len(t_steps)} steps: {t_res}")
    for a in win_acts:
        print(f"    Act: {a['activity_id']} {a['event_time']} {a['target_system']} {a['resource_id']} {a['event_type']} {a['reported_result']}")
