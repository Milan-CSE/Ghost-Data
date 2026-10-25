import csv
cited = {
    'evidence_01', 'evidence_03', 'evidence_05', 'evidence_51', 'evidence_54',
    'evidence_56', 'evidence_57', 'evidence_58', 'evidence_59', 'evidence_61',
    'evidence_92', 'evidence_93', 'evidence_94', 'evidence_02', 'evidence_06'
}
with open('dataset/evidence_files.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['file_id'] in cited:
            print(f"{r['file_id']:12} {r['captured_at']:22} {r['file_path']}")
