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
