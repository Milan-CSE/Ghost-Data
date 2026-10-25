import json
with open('dataset/evidence/records/service_resource_export_20260915_114455.json') as f:
    d = json.load(f)
accs = d['service_exports']['account_service']
print('Type:', type(accs))
if isinstance(accs, list):
    for item in accs:
        if isinstance(item, dict):
            if item.get('resource_id') in {'account_3136', 'account_5684', 'account_5334'}:
                print(item)
