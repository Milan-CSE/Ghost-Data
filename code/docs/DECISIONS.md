# Decisions Log — Ghost Data Still Exists

This file records architecture decisions, assumptions, and rule clarifications adopted during development, referencing `planning/COMBINED_PLAN.md`.

## D-01: Case Ordering in `output.csv` (Patch P1)
- **Decision:** Use natural row order as given in `dataset/deletion_requests.csv` (`case_33` through `case_550`).
- **Rationale:** Part A patch P1 overrides Part B lexicographic ordering. Lexicographic sorting would artificially disrupt sequential request intake order, whereas the official template aligns with natural request order.
- **Guarded By:** Pipeline output tests and configuration `CASE_ORDER = "natural"`.

## D-02: Report Locations and Archive Packaging (Patch P2)
- **Decision:** Generate reports in `code/evaluation/` (`evaluation_report.md`, `usage_report.md`) and package them into root `evaluation/` in `code.zip`.
- **Rationale:** Satisfies both the `README.md` specification (`code/evaluation/`) and the root `AGENTS.md` §6.8 / `problem_statement.md` requirement (`evaluation/`).

## D-03: Unresolved Resource State Fallback (Patch P3)
- **Decision:** Fall back to the latest admissible observation if state cannot be definitively settled, logging any occurrence to `review/unresolved.md`.
- **Rationale:** Evaluation requires deterministic prediction for every owned resource; omission is only valid inside covering stores.

## D-04: Non-Deletion Intent Handling (Patch P4)
- **Decision:** Intent arbitration checks request texts for explicit non-deletion requests, mapping them to `NOT_APPLICABLE` with `[]` steps.

## D-05: Corroboration Role of Activity Logs (Patch P6)
- **Decision:** Activity logs serve strictly as corroborating evidence and resource discovery signals, not absolute ground truth for deletion completion.

## D-06: Step 1 Scaffolding and Acceptance Gates
- **Decision:** Implement canonical step serialization (`code/ghost/steps.py`), row invariant validator (`code/ghost/validate.py`), full evaluation scorer (`code/evaluation/score.py`), and test suites (`tests/test_steps.py`, `tests/test_validate.py`).
- **Rationale:** Locks step ordering and validation invariants upfront before any heuristic or extraction logic is built.

## D-07: Baseline Safety-Net Implementation (Step 2)
- **Decision:** Implement `code/main.py` to deterministically emit all 518 evaluation cases (`case_33` through `case_550`) matching the natural request order and valid `NOT_APPLICABLE` / `[]` schema.
- **Rationale:** Establishes a verified, structurally compliant output artifact early as a submission safety net, with automated file validation stopping any malformed output.
- **Guarded By:** `tests/test_baseline.py` and `ghost.validate.validate_file`.

## D-08: Historical Search Surface Anti-Leakage Invariant (Step 3)
- **Decision:** Identifiers (`email`, `phone`, `email_hash`) that originated in audit log events after `audit_at` are strictly excluded from `IdentityBag.search_surface`.
- **Rationale:** Prevents future temporal leakage during evidence lookup and ensures the agent evaluates compliance solely as of `audit_at`.
- **Guarded By:** `tests/test_identity.py::test_anti_leakage_post_cutoff_exclusion`.

## D-09: Point-in-Time Identity Rollback (Step 3)
- **Decision:** Reconstruct the active identity tuple as of `audit_at` by rolling back future audit log transitions (`event_time > audit_at`) in reverse-chronological order.
- **Rationale:** Resolves whether active direct identifiers remained in account tombstones or customer profiles at the precise audit cutoff.
- **Guarded By:** `tests/test_identity.py::test_rollback_future_audit_events`.

## D-10: Cross-Format Covering Index (Step 3, Defect case_31 Resolution)
- **Decision:** `View.covering_snapshot` indexes all authoritative stores across SQL dumps, JSON snapshot bundles, and ledgers by `captured_at`.
- **Rationale:** Resolves the known `case_31` defect where a single-format SQL selector selected older `evidence_54` instead of newer JSON bundle `evidence_51`.
- **Guarded By:** `tests/test_ledger.py::test_case_31_cross_format_covering_snapshot_selection`.

## D-11: Replication Drift State Priority (Step 3)
- **Decision:** When multiple observations for a resource share the exact latest timestamp, prioritize surviving copies (`PRESENT` / `ACTIVE`).
- **Rationale:** Implements the verified replication drift pattern (e.g., sample `case_05` where failover replica retains data deleted from primary).
- **Guarded By:** `tests/test_ledger.py::test_replication_drift_presence_priority`.

## D-12: Authoritative Covering vs Observation Log Separation (Step 3)
- **Decision:** Full store/table captures set `covers_system=True`. Event logs, syslog streams, PDF documents, and targeted ledger lookups set `covers_system=False`.
- **Rationale:** Omission of a resource indicates `ABSENT` only within authoritative covering snapshots, never within point-in-time observation logs.
- **Guarded By:** Adapter unit tests in `tests/test_adapters.py`.

## D-13: Ownership Linking Hierarchy and Decoy Rejection (Step 4)
- **Decision:** Prioritize grounded evidence matches via `IdentityBag.search_surface` across all adapters, relational catalog rows in `system_activity.csv` (`LINK_RESOURCE_IDENTITY`), and targeted `deletion_worker` corroboration within `[reported_at - 15 min, reported_at + 15 min]` strictly when no account profile was found in evidence. Decoy records with lookalike names or email prefixes are rejected.
- **Rationale:** Prevents spurious cross-case linking while ensuring unevidenced primary accounts deleted prior to snapshot captures are correctly recovered.
- **Guarded By:** `tests/test_ownership.py`.

## D-14: Coverage-Based State Reconstruction and Replica Drift Resolution (Step 4)
- **Decision:** State at `audit_at` is established by the latest admissible observation (`captured_at <= audit_at`). If missing, state resolves to `ABSENT` via omission from an authoritative covering store (`view.covering_snapshot`). When multiple replica observations share the latest timestamp, surviving `PRESENT`/`ACTIVE` data takes precedence over deleted primary records. Patch P3 fallback logs ungrounded items to `review/unresolved.md`.
- **Rationale:** Guarantees deterministic state resolution without inventing citations or assertions of presence.
- **Guarded By:** `tests/test_state.py`.

## D-15: Table-Driven 15-Rule Policy Compilation and Action Invariants (Step 4)
- **Decision:** All 15 rules from `deletion_rules.csv` plus operational `DATA_FLOW` are compiled into a unified table-driven engine preserving exact action counts (7 DELETE, 3 REDACT, 2 ANONYMIZE, 3 RETAIN). Retained records (`SECURITY_AUDIT_LOG`, `LEGAL_HOLD_RECORD`) emit exclusively `VERIFY_RECORD_PRESENT`. Clean tombstones emit only `VERIFY_RECORD_REDACTED`, while dirty tombstones emit finding, redaction, and verification. COMPLETE cases cite evidence for all verifications; INCOMPLETE cases use empty evidence IDs for remediations and verifications.
- **Rationale:** Directly maps specification and policy requirements without case-specific conditional logic.
- **Guarded By:** `tests/test_policy.py`.

