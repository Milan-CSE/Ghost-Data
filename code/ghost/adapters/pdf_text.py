"""Adapter for PDF document text extraction (pdf_text.py)."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from ghost.types import Fact, State

try:
    import pypdf
except ImportError:
    pypdf = None

EMAIL_PATTERN = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
USER_ID_PATTERN = re.compile(r"\buser_\d+\b")
RESOURCE_ID_PATTERN = re.compile(r"\b(?:support_\d+|account_\d+|audit_record_\d+|export_\d+|statement_\d+)\b")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def parse(path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Parse text-extractable PDF files into Fact objects."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    text = ""
    if pypdf is not None:
        try:
            reader = pypdf.PdfReader(str(path))
            text = "\n".join([page.extract_text() or "" for page in reader.pages])
        except Exception:
            text = ""

    if not text:
        return []

    facts: list[Fact] = []

    # Extract all identifiers in document
    emails = set(m.strip() for m in EMAIL_PATTERN.findall(text))
    user_ids = set(m.strip() for m in USER_ID_PATTERN.findall(text))
    hashes = set(_sha256(e) for e in emails)

    # Find resource IDs in document
    res_matches = set(RESOURCE_ID_PATTERN.findall(text))

    # Identify document type and system
    text_lower = text.lower()
    if "support" in text_lower or any("support_" in r for r in res_matches):
        system_id = "support_platform"
        category = "SUPPORT_ATTACHMENT"
    elif "statement" in text_lower or "customer statement" in text_lower:
        system_id = "account_service"
        category = "USER_PROFILE"
    elif "compliance journal" in text_lower or "audit" in text_lower:
        system_id = "security_service"
        category = "SECURITY_AUDIT_LOG"
    elif "disputed orders and tax records" in text_lower or "tax records" in text_lower:
        system_id = "legal_retention_service"
        category = "LEGAL_HOLD_RECORD"
    else:
        system_id = "support_platform"
        category = "SUPPORT_ATTACHMENT"

    if res_matches:
        for rid in res_matches:
            facts.append(
                Fact(
                    file_id=file_id,
                    captured_at=captured_at,
                    system_id=system_id,
                    resource_id=rid,
                    category=category,
                    state=State.PRESENT,
                    emails=frozenset(emails),
                    hashes=frozenset(hashes),
                    user_ids=frozenset(user_ids),
                    phones=frozenset(),
                    store="document_pdf",
                    covers_system=False,
                )
            )

    return facts
