import csv
import json

with open("dataset/deletion_requests.csv", "r", encoding="utf-8") as f:
    cases = list(csv.DictReader(f))

# Let's inspect the last 20 cases
for c in cases[-20:]:
    print(c["case_id"], "-->", repr(c["request_text"]))
