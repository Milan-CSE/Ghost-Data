"""Evidence format adapters router."""
from __future__ import annotations
import json
from pathlib import Path
from ghost.types import Fact
from . import sqlite_dump, json_bundle, json_ledger, log_kv, log_syslog, log_jsonl, handover_txt, pdf_text, png_vision


def parse_evidence_file(file_path: Path | str, file_id: str, captured_at: str) -> list[Fact]:
    """Route evidence file to the appropriate adapter based on extension and contents."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Evidence file not found: {path}")

    ext = path.suffix.lower()

    if ext == ".sql":
        return sqlite_dump.parse(path, file_id, captured_at)

    if ext == ".json":
        # Check whether it's a snapshot bundle or ledger
        try:
            with open(path, "r", encoding="utf-8") as f:
                header = f.read(512)
            if "snapshots" in header:
                return json_bundle.parse(path, file_id, captured_at)
        except Exception:
            pass
        return json_ledger.parse(path, file_id, captured_at)

    if ext == ".log":
        try:
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            if "<" in first_line and ">1" in first_line:
                return log_syslog.parse(path, file_id, captured_at)
            if "{" in first_line and "severity" in first_line:
                return log_jsonl.parse(path, file_id, captured_at)
        except Exception:
            pass
        return log_kv.parse(path, file_id, captured_at)

    if ext == ".txt":
        return handover_txt.parse(path, file_id, captured_at)

    if ext == ".pdf":
        return pdf_text.parse(path, file_id, captured_at)

    if ext == ".png":
        return png_vision.parse(path, file_id, captured_at)

    return []
