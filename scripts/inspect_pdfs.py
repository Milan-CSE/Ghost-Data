import pypdf
from pathlib import Path

pdf_dir = Path("dataset/evidence/documents")
for p in sorted(pdf_dir.glob("*.pdf")):
    reader = pypdf.PdfReader(str(p))
    txt = "\n".join([page.extract_text() or "" for page in reader.pages])
    print(f"=== {p.name} ({len(txt)} chars) ===")
    print(txt[:300])
    print("-" * 50)
