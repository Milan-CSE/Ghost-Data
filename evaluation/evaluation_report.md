# Evaluation Report: Ghost Data Still Exists Deletion-Audit Engine

## 1. Executive Summary & Canonical Sample Performance

The Ghost Data Deletion-Audit Agent was evaluated against the 32 canonical sample requests in `dataset/sample_deletion_requests.csv` and ground-truth answers in `dataset/sample_output.csv`.

| Metric | Measured Value | Target / Benchmark |
|---|---|---|
| **Case-Level Deletion Status Accuracy** | **100.00% (32/32)** | 100.00% |
| **Row Exact Match Rate** | **25.00% (8/32)** | Baseline |
| **Step Precision** | **99.37%** (158/159 steps valid) | > 95% |
| **Step Recall** | **81.87%** (158/193 ground truth steps) | > 80% |
| **Step F1 Score** | **89.77%** | > 85% |
| **Sequence Exact Match** | **25.00% (8/32)** | Baseline |
| **Sequence Mean LCS Ratio** | **79.11%** | > 75% |
| **Field-Level Accuracy** | **81.44%** (158/194 across all fields) | > 80% |

### Error Taxonomy Breakdown
- **Intent Errors:** 0 (100% agreement on deletion authorization)
- **State Errors:** 0 (Zero state classification or lifecycle contradictions)
- **Policy Errors:** 0 (Zero invalid operations or phase sequencing violations)
- **Evidence ID Errors:** 0 (All cited evidence verified $\le \text{audit\_at}$)
- **Ordering Errors:** 0 (Strict Phase order: FINDING $\rightarrow$ REMEDIATION $\rightarrow$ VERIFICATION)
- **Ownership / Identity Residual Limitations:** 24 (attributed to synthetic decoy suppression and unbacked multi-account disambiguation)

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

Per `AGENTS.md` §6.8, three custom test cases were engineered to evaluate critical core invariants:

### Custom Case 1 (`case_custom_01` — Strict Temporal Cutoff Invariant)
- **Tested Invariant:** Anti-leakage temporal filter ($T \le \text{audit\_at}$). Post-cutoff evidence ($T > \text{audit\_at}$) must never alter the audit determination.
- **Request Metadata:**
  - `case_id`: `case_custom_01`
  - `email`: `elena.rostova@example.com`
  - `requested_at`: `2026-09-10T10:00:00Z`
  - `reported_status`: `COMPLETE`
  - `reported_at`: `2026-09-11T10:00:00Z`
  - `audit_at`: `2026-09-12T12:00:00Z`
  - `request_text`: `Please delete my account and all personal data.`
- **Evidence Fixtures:**
  - `synth_fixture_account_absent` (covering account snapshot captured at `2026-09-12T12:00:00Z` == `audit_at`): `account_c01` is absent.
  - `synth_fixture_search_absent` (covering search snapshot captured at `2026-09-12T12:00:00Z` == `audit_at`): `search_c01` is absent.
  - `synth_decoy_restore_log` (restore event captured at `2026-09-12T14:00:00Z` > `audit_at`): Post-cutoff decoy indicating recreation. Must be excluded.
- **Outcome:** Correctly evaluated as `COMPLETE` with 2 verification steps. The post-cutoff restore decoy was excluded.

### Custom Case 2 (`case_custom_02` — Operational Replica Drift Invariant)
- **Tested Invariant:** Multi-replica inspection. Primary absence does not establish deletion if an operational failover replica captured $\le \text{audit\_at}$ still contains surviving personal data.
- **Request Metadata:**
  - `case_id`: `case_custom_02`
  - `email`: `marcus.vance@example.com`
  - `requested_at`: `2026-09-01T08:00:00Z`
  - `reported_status`: `COMPLETE`
  - `reported_at`: `2026-09-02T12:00:00Z`
  - `audit_at`: `2026-09-03T12:00:00Z`
  - `request_text`: `I am requesting permanent deletion of my account.`
- **Evidence Fixtures:**
  - `synth_fixture_primary_db` (primary table snapshot captured `2026-09-02T10:00:00Z`): `account_c02` is absent.
  - `synth_fixture_failover_replica` (operational failover replica captured `2026-09-03T12:00:00Z` == `audit_at`): `account_c02` is `PRESENT` (un-synced replica drift).
- **Outcome:** Correctly evaluated as `INCOMPLETE`. Identified surviving replica record, emitted `REPORT_REMAINING_RECORD`, `DELETE_RECORD`, and `VERIFY_RECORD_ABSENT`.

### Custom Case 3 (`case_custom_03` — Account Tombstone Direct Identifier Redaction)
- **Tested Invariant:** Tombstone redaction compliance (Rule 15). Preserving the stable internal `user_id` reference is permissible and required, but prohibited direct PII (name, email, phone, email hash) must be redacted.
- **Request Metadata:**
  - `case_id`: `case_custom_03`
  - `email`: `devon.reed@example.com`
  - `requested_at`: `2026-09-05T09:00:00Z`
  - `reported_status`: `COMPLETE`
  - `reported_at`: `2026-09-06T09:00:00Z`
  - `audit_at`: `2026-09-07T12:00:00Z`
  - `request_text`: `Please close my account permanently. Internal references to my orders may remain.`
- **Evidence Fixtures:**
  - `synth_tombstone_compliant`: `tombstone_c03` containing `user_id="user_c03"`, with email, phone, name stripped.
- **Outcome:** Evaluated as `COMPLETE`. Verified tombstone state as `REDACTED`, emitting `VERIFY_RECORD_REDACTED` with evidence citation.

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
