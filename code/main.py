"""Ghost Data Still Exists — Main Entry Point.

Orchestrates the full deletion-audit engine across all 518 evaluation requests,
enforcing intent classification, identity resolution, admissible ledger views,
ownership linking, point-in-time state reconstruction, and policy compilation.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

# Handle imports whether executed directly, from repo root, or as a package
try:
    from ghost.config import DELETION_REQUESTS_PATH, OUTPUT_PATH, DATASET_DIR, CASE_ORDER
    from ghost.validate import validate_file
    from ghost.pipeline import AuditContext, run_case
except ImportError:
    from code.ghost.config import DELETION_REQUESTS_PATH, OUTPUT_PATH, DATASET_DIR, CASE_ORDER
    from code.ghost.validate import validate_file
    from code.ghost.pipeline import AuditContext, run_case


def load_request_cases(requests_path: Path | str = DELETION_REQUESTS_PATH) -> list[str]:
    """Load case IDs from deletion_requests.csv adhering to CASE_ORDER."""
    requests_path = Path(requests_path)
    if not requests_path.exists():
        raise FileNotFoundError(f"Deletion requests file not found: {requests_path}")

    case_ids = []
    with open(requests_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            case_ids.append(row["case_id"])

    if CASE_ORDER == "lexicographic":
        case_ids.sort()
    # "natural" preserves the exact order from the requests file / template

    return case_ids


def generate_baseline_output(
    output_path: Path | str = OUTPUT_PATH,
    requests_path: Path | str = DELETION_REQUESTS_PATH,
) -> Path:
    """Generate minimal deterministic baseline output.csv (preserved for testing)."""
    out_path = Path(output_path)
    case_ids = load_request_cases(requests_path)

    fieldnames = ["case_id", "deletion_status", "steps_json"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for cid in case_ids:
            writer.writerow({
                "case_id": cid,
                "deletion_status": "NOT_APPLICABLE",
                "steps_json": "[]",
            })

    return out_path


def run_audit_pipeline(
    output_path: Path | str = OUTPUT_PATH,
    requests_path: Path | str = DELETION_REQUESTS_PATH,
    dataset_dir: Path | str = DATASET_DIR,
) -> Path:
    """Execute the full deletion-audit pipeline across all 518 evaluation requests."""
    out_path = Path(output_path)
    req_path = Path(requests_path)
    if not req_path.exists():
        raise FileNotFoundError(f"Deletion requests file not found: {req_path}")

    ctx = AuditContext.load(dataset_dir)

    with open(req_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if CASE_ORDER == "lexicographic":
        rows.sort(key=lambda r: r["case_id"])

    fieldnames = ["case_id", "deletion_status", "steps_json"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            status, steps_json = run_case(row, ctx)
            writer.writerow({
                "case_id": row["case_id"],
                "deletion_status": status,
                "steps_json": steps_json,
            })

    return out_path


def main() -> None:
    """CLI entry point: run full deletion-audit pipeline and validate."""
    print("=" * 60)
    print("GHOST DATA AUDIT AGENT — FULL EVALUATION RUN")
    print("=" * 60)
    print(f"Reading requests from: {DELETION_REQUESTS_PATH}")
    print(f"Target output file:    {OUTPUT_PATH}")

    out_path = run_audit_pipeline()

    print(f"Generated {out_path.name}. Running output validator...")
    errs = validate_file(out_path, expected_count=518)
    if errs:
        print(f"VALIDATION FAILED with {len(errs)} error(s):")
        for err in errs[:10]:
            print(f"  - {err}")
        if len(errs) > 10:
            print(f"  ... and {len(errs) - 10} more.")
        sys.exit(1)

    print("VALIDATION PASSED: 0 errors.")
    print("Status: 518 cases successfully audited with valid schema and JSON.")
    print("=" * 60)


if __name__ == "__main__":
    main()

