"""Ghost Data Still Exists — Main Entry Point.

BASELINE SAFETY-NET IMPLEMENTATION (Build Order Step 2):
This baseline produces a structurally valid 518-row output.csv matching all schema
and validator invariants. It establishes the baseline safety net per Part A of
planning/COMBINED_PLAN.md.

Note: Deletion decisions, evidence citations, and remediation steps are placeholders
(NOT_APPLICABLE / []) in this baseline stage. Detailed identity resolution, evidence
adapters, ownership linking, state reconstruction, policy compilation, and intent
classification will be integrated in subsequent stages.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

# Handle imports whether executed directly, from repo root, or as a package
try:
    from ghost.config import DELETION_REQUESTS_PATH, OUTPUT_PATH, CASE_ORDER
    from ghost.validate import validate_file
except ImportError:
    from code.ghost.config import DELETION_REQUESTS_PATH, OUTPUT_PATH, CASE_ORDER
    from code.ghost.validate import validate_file


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
    """Generate minimal deterministic baseline output.csv for all evaluation requests."""
    out_path = Path(output_path)
    case_ids = load_request_cases(requests_path)

    # Write output.csv with exact required header
    fieldnames = ["case_id", "deletion_status", "steps_json"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for cid in case_ids:
            # Baseline safety-net: structurally valid NOT_APPLICABLE row with empty steps
            writer.writerow({
                "case_id": cid,
                "deletion_status": "NOT_APPLICABLE",
                "steps_json": "[]",
            })

    return out_path


def main() -> None:
    """CLI entry point: run baseline generation and validate."""
    print("=" * 60)
    print("GHOST DATA AUDIT AGENT — BASELINE SAFETY-NET RUN (STEP 2)")
    print("=" * 60)
    print(f"Reading requests from: {DELETION_REQUESTS_PATH}")
    print(f"Target output file:    {OUTPUT_PATH}")

    out_path = generate_baseline_output()

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
    print("Status: 518 cases successfully emitted with valid schema and JSON.")
    print("NOTE: Baseline safety-net run complete. Full deletion auditing to be implemented in Step 3+.")
    print("=" * 60)


if __name__ == "__main__":
    main()
