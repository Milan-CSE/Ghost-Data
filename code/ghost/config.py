"""Configuration paths and constants for ghost data deletion audit."""
from __future__ import annotations
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CODE_DIR = REPO_ROOT / "code"
DATASET_DIR = REPO_ROOT / "dataset"
EVIDENCE_DIR = DATASET_DIR / "evidence"
OUTPUT_PATH = REPO_ROOT / "output.csv"

# Dataset inputs
SAMPLE_REQUESTS_PATH = DATASET_DIR / "sample_deletion_requests.csv"
SAMPLE_OUTPUT_PATH = DATASET_DIR / "sample_output.csv"
DELETION_REQUESTS_PATH = DATASET_DIR / "deletion_requests.csv"
DELETION_RULES_PATH = DATASET_DIR / "deletion_rules.csv"
USER_IDENTITIES_PATH = DATASET_DIR / "user_identities.csv"
USER_AUDIT_LOG_PATH = DATASET_DIR / "user_audit_log.csv"
SYSTEM_ACTIVITY_PATH = DATASET_DIR / "system_activity.csv"
EVIDENCE_FILES_PATH = DATASET_DIR / "evidence_files.csv"

# Ordering convention: natural ordering matches deletion_requests.csv (Part A, Patch P1)
CASE_ORDER = "natural"
