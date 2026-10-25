# Evaluation Report: Ghost Data Still Exists Deletion-Audit Engine

## 1. Executive Summary & Canonical Sample Performance

The Ghost Data Deletion-Audit Agent was evaluated against the 32 canonical sample requests in `dataset/sample_deletion_requests.csv` and ground-truth answers in `dataset/sample_output.csv`.

| Metric | Measured Value | Target / Benchmark |
|---|---|---|
| **Case-Level Deletion Status Accuracy** | **100.00% (32/32)** | 100.00% |
| **Row Exact Match Rate** | **28.12% (9/32)** | Baseline |
| **Step Precision** | **100.00%** (158/158 steps valid) | > 95% |
| **Step Recall** | **81.87%** (158/193 ground truth steps) | > 80% |
| **Step F1 Score** | **90.03%** | > 85% |
| **Sequence Exact Match** | **28.12% (9/32)** | Baseline |
| **Sequence Mean LCS Ratio** | **79.40%** | > 75% |
| **Field-Level Accuracy** | **81.87%** (158/193 across all fields) | > 80% |

### Error Taxonomy Breakdown
- **Intent Errors:** 0 (100% agreement on deletion authorization)
- **State Errors:** 0 (Zero state classification or lifecycle contradictions)
- **Policy Errors:** 0 (Zero invalid operations or phase sequencing violations)
- **Evidence ID Errors:** 0 (All cited evidence verified $\le \text{audit\_at}$)
- **Ordering Errors:** 0 (Strict Phase order: FINDING $\rightarrow$ REMEDIATION $\rightarrow$ VERIFICATION)
- **Ownership / Identity Residual Limitations:** 23 (attributed to synthetic decoy suppression and unbacked multi-account disambiguation)

---

## 2. Evaluation of Non-Deletion Requests (10 Requests)

Under official challenge rules (`problem_statement.md`, `AGENTS.md` §6.5), `request_text` is the primary legal authority for subject intent; reported workflow statuses and system activity logs are internal claims. The engine executes a six-tier arbitration hierarchy that treats request text and evidence as untrusted data.

In `dataset/deletion_requests.csv` (518 total requests), exactly 10 requests do not authorize deletion and are arbitrated as `NOT_APPLICABLE` with `steps_json = "[]"`:

| Case ID | Subject Email | Request Text (Excerpt) | Classified Tier | Evidence-Based Reasoning & Telemetry Corroboration |
|---|---|---|---|---|
| `case_533` | `haruka-kato@gmail.com` | "The mobile number on my profile is out of date. Please replace it with the new one and leave the account active." | Tier 2/3 (Negation/Retention) | Profile data update only; explicit imperative retention: "leave the account active". Corroborated by `activity_3789` (`account_1733`). |
| `case_534` | `mlim7637@gmail.com` | "Please stop the promotional emails. I still need the account and my order history, so I am not asking for deletion." | Tier 3 (Target Negation) | Marketing opt-out only; explicit target-scoped negation: "not asking for deletion", "still need the account". Corroborated by `activity_3741`/`3778`. |
| `case_535` | `gabriel.l5556@outlook.com` | "I'd like to download my account information in a portable format. Please keep the account as it is." | Tier 2/3 (Portability/Retention) | Data portability request; explicit account retention clause: "Please keep the account as it is". Corroborated by `activity_3741`. |
| `case_536` | `aditi.mehta@outlook.com` | "I can't access my profile and need help resetting the login. Do not close the account." | Tier 2/3 (Target Negation) | Technical support / credential recovery inquiry; explicit imperative command: "Do not close the account". Corroborated by `activity_3659`. |
| `case_537` | `l.alvarez94@yahoo.com` | "My surname is misspelled on the account. Can you correct it without removing any of my records?" | Tier 2/3 (Rectification/Retention) | Data rectification under GDPR Art. 16; explicit negative clause: "without removing any of my records". Corroborated by `activity_3618`/`3648`. |
| `case_538` | `morgan.amelia@icloud.com` | "Please remove me from marketing lists only. I still want receipts and service messages for this account." | Tier 3 (Scope Restriction) | Marketing restriction only; explicit boundary adverb "only" with account retention mandate: "still want receipts and service messages". Corroborated by `activity_3618`. |
| `case_539` | `leonie-rousseau@proton.me` | "Can you tell me what personal information you hold about me? This is an information request, not a request to erase it." | Tier 2/3 (Informational Negation) | Subject access request (GDPR Art. 15); explicit negation: "This is an information request, not a request to erase it". Corroborated by `activity_3531`. |
| `case_540` | `ieriksen5151@fastmail.com` | "I need a copy of last year's invoices for my records. Please leave my profile and purchase history in place." | Tier 2/3 (Access/Retention) | Financial document retrieval; explicit retention directive: "Please leave my profile and purchase history in place". Corroborated by `activity_3486`/`3512`. |
| `case_541` | `elena.h3070@zoho.com` | "Please change the email address used for this account. I want to continue using the service." | Tier 2/3 (Account Update) | Credential modification; explicit continuation mandate: "I want to continue using the service". Corroborated by `activity_3486`. |
| `case_542` | `omar.nasser@gmail.com` | "Could you send me a copy of the information held on my account? I still use it, so please don't delete or change anything." | Tier 2/3 (Access/Negation) | Subject access inquiry; explicit negative imperative: "please don't delete or change anything". Corroborated by `activity_3827`. |

---

## 3. Participant-Created Evaluation Cases

Per `AGENTS.md` §6.8 and `COMBINED_PLAN.md` Part A Patch P7, eight synthetic evaluation cases were engineered and verified in `tests/test_custom_cases.py` to evaluate critical core invariants:

### Custom Case 1 (`case_custom_01` — Strict Temporal Cutoff Invariant)
- **Tested Invariant:** Anti-leakage temporal filter ($T \le \text{audit\_at}$). Post-cutoff evidence ($T > \text{audit\_at}$) must never alter the audit determination.
- **Request Metadata:**
  - `case_id`: `case_custom_01`
  - `email`: `elena.rostova@example.com`
  - `requested_at`: `2026-09-10T10:00:00Z`
  - `reported_status`: `COMPLETE`
  - `reported_at`: `2026-09-11T10:00:00Z`
  - `audit_at`: `2026-09-10T12:00:00Z`
  - `request_text`: `Please delete my account and all personal data.`
- **Evidence Fixtures:**
  - `ev_admissible` (captured at `2026-09-10T12:00:00Z` == `audit_at`): `acc_01` is `ABSENT`.
  - `ev_post_cutoff_decoy` (captured at `2026-09-10T14:00:00Z` > `audit_at`): `acc_01` is `PRESENT` (post-cutoff decoy).
- **Outcome:** Evaluated as `COMPLETE`. Post-cutoff decoy strictly excluded from the point-in-time view; only admissible evidence cited.

### Custom Case 2 (`case_custom_02` — Operational Replica Drift Invariant)
- **Tested Invariant:** Multi-replica inspection. Primary database absence does not establish deletion if an operational failover replica captured $\le \text{audit\_at}$ still contains surviving personal data.
- **Request Metadata:**
  - `case_id`: `case_custom_02`
  - `email`: `c02@example.com`
  - `requested_at`: `2026-09-01T08:00:00Z`
  - `reported_status`: `COMPLETE`
  - `reported_at`: `2026-09-02T12:00:00Z`
  - `audit_at`: `2026-09-03T12:00:00Z`
  - `request_text`: `Delete my account permanently`
- **Evidence Fixtures:**
  - `ev_primary` (primary table snapshot captured `2026-09-02T10:00:00Z`): `acc_02` is `ABSENT`.
  - `ev_replica` (failover replica snapshot captured `2026-09-03T12:00:00Z` == `audit_at`): `acc_02` is `PRESENT`.
- **Outcome:** Correctly evaluated as `INCOMPLETE`. Identified replica drift, emitting `REPORT_REMAINING_RECORD`, `DELETE_RECORD`, and `VERIFY_RECORD_ABSENT`.

### Custom Case 3 (`case_custom_03` — Account Tombstone Direct Identifier Redaction)
- **Tested Invariant:** Tombstone redaction compliance (Rule 15). Preserving the stable internal `user_id` reference is permissible and required, but prohibited direct PII (name, email, phone, email hash) must be redacted.
- **Request Metadata:**
  - `case_id`: `case_custom_03`
  - `email`: `c03@example.com`
  - `requested_at`: `2026-09-05T09:00:00Z`
  - `reported_status`: `COMPLETE`
  - `reported_at`: `2026-09-06T09:00:00Z`
  - `audit_at`: `2026-09-07T12:00:00Z`
  - `request_text`: `Close my account`
- **Evidence Fixtures:**
  - `ev_tombstone`: `acc_03` containing `user_id="user_c03"`, with email, phone, name stripped. State is `REDACTED`.
- **Outcome:** Evaluated as `COMPLETE`. Verified tombstone state as `REDACTED`, emitting `VERIFY_RECORD_REDACTED` citing `ev_tombstone`.

### Custom Case 4 (`case_custom_04` — Uppercase and Mixed-Case Email Resolution)
- **Tested Invariant:** Case-insensitive normalization across requests, identities, and historical audit logs.
- **Request Metadata:**
  - `case_id`: `case_custom_04`
  - `email`: `DEVON.SMITH@EXAMPLE.COM` (uppercase)
  - `audit_at`: `2026-09-01T00:00:00Z`
- **Identity Fixture:**
  - `user_c04`: `name="Devon Smith"`, `email="devon.smith@example.com"`, `email_hash="hash04"`.
- **Outcome:** Reconstructed `IdentityBag` matches `user_c04` exactly, normalizing email to lowercase and including hash in `search_surface`.

### Custom Case 5 (`case_custom_05` — Historical-Only Email Rollback / Recovery)
- **Tested Invariant:** Historical email resolution via `user_audit_log.csv` without leaking post-cutoff identities.
- **Request Metadata:**
  - `case_id`: `case_custom_05`
  - `email`: `elena.old@example.com` (superseded prior to current snapshot)
- **Audit Log Fixture:**
  - Email changed from `elena.old@example.com` to `elena.new@example.com` at `2026-08-15T00:00:00Z`.
- **Outcome:** For `audit_at=2026-08-10`, resolves `user_c05` with `active_at_audit["email"] = "elena.old@example.com"` and strictly excludes `elena.new@example.com` from search surface. For `audit_at=2026-08-20`, includes both in search surface.

### Custom Case 6 (`case_custom_06` — Decoy Name Rejection)
- **Tested Invariant:** Decoy suppression. Resources sharing a subject's name but distinct user IDs or emails are never linked.
- **Request Metadata:**
  - `case_id`: `case_custom_06`
  - `email`: `alex.taylor@example.com`, subject `user_target`.
- **Evidence Fixtures:**
  - `acc_target`: `user_id="user_target"`.
  - `acc_decoy`: `user_id="user_decoy"` (same name, decoy user ID).
- **Outcome:** `acc_target` linked successfully; `acc_decoy` strictly rejected.

### Custom Case 7 (`case_custom_07` — Backup Restore Blocked vs Allowed Predicates)
- **Tested Invariant:** Backup restore predicates under Rule 14. An active restore path requires `BLOCK_RESTORE` remediation; an established blocked restore passes verification.
- **Request Metadata:**
  - `case_id`: `case_c07`
  - `audit_at`: `2026-09-03T00:00:00Z`
- **Evidence Fixtures:**
  - Sub-case A: `backup_archive_01` has `state=ACTIVE`. Emits `REPORT_RESTORE_RISK`, `BLOCK_RESTORE`, `VERIFY_RESTORE_BLOCKED` (`INCOMPLETE`).
  - Sub-case B: `backup_archive_02` has `state=BLOCKED`. Emits `VERIFY_RESTORE_BLOCKED` (`COMPLETE`).
- **Outcome:** Accurately branches between finding/remediation and evidence-backed verification.

### Custom Case 8 (`case_custom_08` — Tombstone Dirty (PII Exposed) vs Clean)
- **Tested Invariant:** Handling dirty tombstones where prohibited direct identifiers (email/phone) remain present.
- **Request Metadata:**
  - `case_id`: `case_c08`
  - `audit_at`: `2026-09-03T00:00:00Z`
- **Evidence Fixtures:**
  - `acc_dirty`: `category="ACCOUNT_TOMBSTONE"`, but retains `emails=["c08@example.com"]`. State is `PRESENT`.
- **Outcome:** Evaluated as `INCOMPLETE`. Correctly emits `REPORT_EXPOSED_PII`, `REDACT_RECORD`, and `VERIFY_RECORD_REDACTED`.

---

## 4. Failures Discovered and Iterative Improvements

1. **Intake Window Over-Broadening (Patch P6):**
   - *Issue:* Corroboration window was previously widened by 2 hours before `requested_at` and 15 minutes after `reported_at`, capturing un-related events.
   - *Fix:* Constrained activity corroboration strictly to `[requested_at, reported_at]` per specification. Prohibited activity from establishing primary ownership independently.

2. **Dual Fallback Semantics (Patch P3):**
   - *Issue:* When a resource had an observation pre-dating the reported workflow cutoff, the observation was preserved but logged as resolved.
   - *Fix:* Clarified P3 dual fallback: preserved the last admissible observation as the deterministic state while recording uncertainty in `review/unresolved.md` and setting `is_unresolved=True`.

3. **Multimodal Vision Integration:**
   - *Issue:* 11 administrative console screenshots in `evidence/images/` were previously deferred, causing missing observations on `case_34` and `case_46`.
   - *Fix:* Built multimodal table extraction via `gemini-3.1-flash-lite`, strictly schema-validating extracted records to Fact objects, caching by image SHA-256 hash, and logging low-confidence records to `review/vision_confidence.md`.

4. **Tombstone Lifecycle Temporal Filtering (solving `case_17`):**
   - *Issue:* In `case_17` (requested August 2026), an `ACCOUNT_TOMBSTONE` observation from March 2026 (`evidence_42`, generated during a prior request `case_46`) was linked to the case, causing an unexpected tombstone verification step and a fallback.
   - *Fix:* Added an invariant guard in `code/ghost/ownership.py`: an `ACCOUNT_TOMBSTONE` observation cannot predate the current request intake (`fact.captured_at >= requested_at`). This immediately elevated `case_17` to a 100% byte-exact ground-truth match (raising exact match rate to 28.12% / 9/32) and eliminated all fallbacks across canonical samples.

5. **Evidence Namespace Integrity & Order Number Exclusion:**
   - *Issue:* An experiment matching order IDs (`ORD-xxxx`) in PDF documents caused transactional order references in customer support attachments (`evidence_58`) to be erroneously parsed as platform resources, generating three spurious steps in `case_07` and dropping step precision to 98.14%.
   - *Fix:* Restricted PDF resource extraction strictly to authoritative platform resource namespaces (`support_\d+`, `account_\d+`, `audit_record_\d+`, `export_\d+`, `statement_\d+`), excluding transactional order and statement references. Validated via regression test `test_pdf_support_attachment_order_number_exclusion`, restoring 100.00% step precision (158/158).

6. **Ordering Invariant & Topological Verification:**
   - *Issue:* Potential ordering ambiguities between process flow remediation (`DISABLE_DATA_FLOW`, `BLOCK_RESTORE`) and resource remediation (`DELETE_RECORD`, `REDACT_RECORD`).
   - *Fix:* Topological sorting in `code/ghost/steps.py` guarantees strict monotonic ordering: `FINDING` $\rightarrow$ `REMEDIATION` (flows first) $\rightarrow$ `VERIFICATION`. Verified across all 518 cases (2,621 emitted steps) with 0 ordering violations.

7. **Prompt Injection Hardening & Untrusted Inert Data:**
   - *Issue:* Request texts or evidence strings could attempt prompt injection to override deletion intent or bypass compliance verification.
   - *Fix:* Architected intent classification and evidence parsing so that all input strings are treated strictly as inert data. Added a dedicated test suite (`tests/test_security_injection.py`) covering 7 injection attack patterns (access-request overrides, administrative claims, XML tag escapes, shell payloads).

8. **Idempotent Uncertainty Tracking:**
   - *Issue:* Re-running evaluation repeatedly appended duplicate entries to `review/unresolved.md`.
   - *Fix:* Added idempotence checking in `code/ghost/state.py` (`_record_unresolved_entry`) to ensure exactly one line per unresolved resource is logged.
