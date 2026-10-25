"""Tests for the minimal deterministic baseline (code/main.py)."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import pytest
from main import generate_baseline_output, load_request_cases
from ghost.config import DELETION_REQUESTS_PATH, OUTPUT_PATH, REPO_ROOT
from ghost.validate import validate_file, check_row


def test_request_case_loading():
    """Ensure all 518 cases are loaded from deletion_requests.csv without duplicates."""
    cases = load_request_cases(DELETION_REQUESTS_PATH)
    assert len(cases) == 518
    assert len(set(cases)) == 518
    assert cases[0] == "case_33"
    assert cases[-1] == "case_550"


def test_baseline_generation_and_schema(tmp_path: Path):
    """Verify output file schema, header, column count, and row count."""
    out_csv = tmp_path / "output.csv"
    generated_path = generate_baseline_output(output_path=out_csv)
    assert generated_path.exists()

    with open(generated_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == ["case_id", "deletion_status", "steps_json"]

        rows = list(reader)
        assert len(rows) == 518

        for line_no, row in enumerate(rows, start=2):
            assert len(row) == 3, f"Line {line_no} does not have 3 columns"
            case_id, status, steps_json = row
            assert status in {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
            parsed_steps = json.loads(steps_json)
            assert isinstance(parsed_steps, list)


def test_baseline_case_coverage(tmp_path: Path):
    """Verify exact case coverage and ordering match deletion_requests.csv."""
    expected_cases = load_request_cases(DELETION_REQUESTS_PATH)
    out_csv = tmp_path / "output.csv"
    generate_baseline_output(output_path=out_csv)

    with open(out_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        actual_cases = [r["case_id"] for r in reader]

    assert actual_cases == expected_cases


def test_baseline_passes_validator(tmp_path: Path):
    """Verify the generated baseline output passes the output validator with 0 errors."""
    out_csv = tmp_path / "output.csv"
    generate_baseline_output(output_path=out_csv)

    errs = validate_file(out_csv, expected_count=518)
    assert errs == [], f"Validation errors found: {errs}"


def test_baseline_deterministic_output(tmp_path: Path):
    """Verify generating baseline output twice produces byte-identical results."""
    out1 = tmp_path / "output_1.csv"
    out2 = tmp_path / "output_2.csv"

    generate_baseline_output(output_path=out1)
    generate_baseline_output(output_path=out2)

    hash1 = hashlib.sha256(out1.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(out2.read_bytes()).hexdigest()

    assert hash1 == hash2, "Baseline generation is not deterministic!"


def test_root_output_csv_exists_and_valid():
    """Verify root output.csv exists and satisfies all validation invariants."""
    assert OUTPUT_PATH.exists(), f"Root output.csv missing at {OUTPUT_PATH}"
    errs = validate_file(OUTPUT_PATH, expected_count=518)
    assert errs == [], f"Root output.csv validation errors: {errs}"


def test_production_pipeline_sample_determinism():
    """Verify full audit pipeline execution is byte-for-byte deterministic across runs."""
    from ghost.pipeline import AuditContext, run_case
    from ghost.config import DATASET_DIR, SAMPLE_REQUESTS_PATH

    ctx = AuditContext.load(DATASET_DIR)
    with open(SAMPLE_REQUESTS_PATH, "r", encoding="utf-8") as f:
        samples = list(csv.DictReader(f))[:5]

    for req in samples:
        st1, json1 = run_case(req, ctx)
        st2, json2 = run_case(req, ctx)
        assert st1 == st2, f"Status mismatch for {req['case_id']}"
        assert json1 == json2, f"JSON step serialization mismatch for {req['case_id']}"

