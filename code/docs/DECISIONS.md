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

## D-16: Patch P3 Dual Fallback Alignment & Deletion-Worker Category Mapping
- **Decision:** Aligned unresolved state fallback strictly to Patch P3:
  1. When a resource has an earlier admissible observation but no newer observation post-dating the reported workflow resolves the state, the last admissible observation is preserved as the deterministic state, uncertainty is recorded in `review/unresolved.md`, and `is_unresolved=True` is marked rather than treating the fallback as fully resolved.
  2. When a resource has no admissible observation and is not omitted from an authoritative covering store, safe existence (`State.PRESENT` or `State.ACTIVE`) is preserved rather than inventing absence, logging to `review/unresolved.md` with `is_unresolved=True`.
  3. Refined resource data categories using the deletion worker's targeted operation (`DELETE_RECORD` on support -> `SUPPORT_ATTACHMENT`, `REDACT_RECORD` on support -> `SUPPORT_MESSAGE`, `DELETE_RECORD` on analytics -> `MARKETING_PROFILE`).
  4. Invariant P6 corroboration: evaluated strictly within `[requested_at, reported_at]` on already-grounded resources, never establishing primary ownership on its own.
- **Rationale:** Ensures zero ungrounded absence claims, accurately tracks and logs all unresolved fallback occurrences, and guarantees deterministic step generation without serializing unsupported state strings.
- **Guarded By:** `tests/test_state.py`, `tests/test_ownership.py`.

## D-17: Six-Tier Intent Arbitration, Multimodal Vision, and Telemetry Integration (Step 5)
- **Decision:** Implemented the six-tier intent classification hierarchy (`code/ghost/intent.py`) enforcing clause-level syntactic precedence (normalization, informational/hypothetical filter, target-scoped negation, affirmative deletion mandate, scoped intake telemetry, conservative fallback). Integrated multimodal vision extraction (`code/ghost/vision.py`, `code/ghost/adapters/png_vision.py`) using `gemini-3.1-flash-lite` for all 11 administrative console screenshot artifacts, with schema validation, confidence flagging (< 0.8) to `review/vision_confidence.md`, and deterministic SHA-256 disk caching. Implemented centralized LLM client (`code/ghost/llm.py`) with fail-loud credential enforcement and telemetry logging to `runs/<run_id>/telemetry.jsonl`.
- **Rationale:** Accurately separates valid deletion authorizations from non-deletion requests (identifying exactly 10 non-deletion requests across 518 evaluation cases), establishes evidence from previously inaccessible administrative screenshots with zero ungrounded absence claims, and maintains full token and cost accountability without leaking secrets.
- **Guarded By:** `tests/test_intent.py`, `tests/test_vision_llm.py`, `evaluation/evaluation_report.md`, `evaluation/usage_report.md`.

## D-18: Weak-Spot Pass Hardening, Tombstone Lifecycle Guard, and Synthetic Invariant Verification (Step 6)
- **Decision:** Completed comprehensive weak-spot hardening pass per `COMBINED_PLAN.md` Part A:
  1. **Tombstone Lifecycle Temporal Guard:** Enforced `fact.captured_at >= requested_at` for `ACCOUNT_TOMBSTONE` records in `OwnershipLinker`, preventing prior-lifecycle tombstones from linking to a subsequent deletion lifecycle. Resolved `case_17` to a 100% byte-exact ground-truth match, raised the canonical sample exact match rate to 28.12% (9/32), and eliminated all fallbacks across sample cases (0 fallbacks on samples; exactly 3 across all 518 evaluation cases).
  2. **Platform Resource Namespace Discipline:** Kept PDF resource extraction strictly bounded to authoritative platform resource namespaces (`support_\d+`, `account_\d+`, `audit_record_\d+`, `export_\d+`, `statement_\d+`), avoiding regex contamination from transactional order references (`ORD-xxxx`) which caused spurious false positives in `case_07`. Guarded by `tests/test_adapters.py::test_pdf_support_attachment_order_number_exclusion`, restoring 100.00% step precision (158/158).
  3. **Topological Ordering Invariant:** Verified that `code/ghost/steps.py` guarantees strict monotonic ordering (`FINDING` -> `REMEDIATION` with process flows first -> `VERIFICATION`), with consecutive numbering from 1. Confirmed zero ordering violations across all 518 cases (2,621 steps).
  4. **Untrusted Data & Prompt Injection Hardening:** Architected the pipeline to treat all request text and evidence contents strictly as inert data strings, verified through a dedicated regression test suite (`tests/test_security_injection.py`) covering 7 adversarial injection vectors.
  5. **Mandatory Synthetic Evaluation Coverage (Patch P7):** Implemented and verified eight custom evaluation cases in `tests/test_custom_cases.py` and documented them in `evaluation/evaluation_report.md` (temporal cutoff exclusion, operational replica drift, tombstone direct identifier redaction, uppercase/mixed-case email resolution, historical email rollback, decoy name rejection, backup restore blocked vs allowed, and tombstone dirty vs clean).
  6. **Idempotent Uncertainty Tracking:** Enhanced `_record_unresolved_entry` in `code/ghost/state.py` to prevent duplicate log pollution in `review/unresolved.md`.
- **Rationale:** Eliminates subtle temporal leakage across multi-request lifecycles, guarantees parsing robustness across non-standard business artifacts, ensures prompt injection resistance, and provides comprehensive regression protection for all critical core invariants.
- **Guarded By:** `tests/test_security_injection.py`, `tests/test_custom_cases.py`, `review/unresolved.md`, `evaluation/evaluation_report.md`.

