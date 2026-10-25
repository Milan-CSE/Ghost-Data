import csv

with open("dataset/deletion_requests.csv", "r", encoding="utf-8") as f:
    cases = list(csv.DictReader(f))

non_deletion_cids = {f"case_{i}" for i in range(533, 543)}
print(f"Known non-deletion count: {len(non_deletion_cids)}")

other_cases = [c for c in cases if c["case_id"] not in non_deletion_cids]
print(f"Other cases count: {len(other_cases)}")

# Let's inspect other cases for any negative words or question marks
suspicious = []
for c in other_cases:
    txt = c["request_text"].lower()
    if "?" in txt or "not" in txt or "keep" in txt or "leave" in txt:
        suspicious.append((c["case_id"], c["request_text"]))

print(f"Suspicious cases in other 508: {len(suspicious)}")
for cid, txt in suspicious[:10]:
    print(cid, "-->", repr(txt))
