import csv

with open("dataset/sample_deletion_requests.csv", "r", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        s = r["request_text"].encode("ascii", "backslashreplace").decode("ascii")
        print(f"{r['case_id']}: {s}")
