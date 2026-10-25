import csv

with open("dataset/deletion_requests.csv", "r", encoding="utf-8") as f:
    cases = list(csv.DictReader(f))

first_sentences = set()
for c in cases:
    txt = c["request_text"].split(".")[0].strip()
    first_sentences.add(txt)

print(f"Total unique first sentences: {len(first_sentences)}")
for idx, s in enumerate(sorted(first_sentences), 1):
    safe_s = s.encode("ascii", "backslashreplace").decode("ascii")
    print(f"{idx}: {safe_s}")
