# Model Usage & Telemetry Report

This report summarizes model utilization and telemetry recorded during the evaluation run of the Ghost Data Deletion-Audit Engine across all 518 requests.

## 1. Overview & Architecture Boundary

Per project design specifications (`COMBINED_PLAN.md` §5.8), model invocations are strictly bounded:
1. **Multimodal Table Extraction:** Used exclusively for administrative console screenshot artifacts (`dataset/evidence/images/*.png`) where relational database exports, logs, or JSON records are not provided.
2. **Intent Arbitration:** Used as an optional fallback for obscure natural language request texts that cannot be resolved through the deterministic six-tier hierarchy (Tiers 1–5).
3. **Core Pipeline:** Identity resolution, ledger temporal views, ownership linking, state reconstruction, and policy compilation are 100% deterministic and execute with zero model token overhead.

All model calls are centralized through `code/ghost/llm.py` with temperature 0.0, strict JSON schema validation, disk caching keyed by `sha256(model + prompt + image)`, and run telemetry appended to `runs/<run_id>/telemetry.jsonl`.

---

## 2. Full Evaluation Run Usage Summary (518 Requests)

| Metric | Multimodal Vision (Screenshots) | Intent Arbitration | Total / Aggregate |
|---|---|---|---|
| **Model Provider** | Google Cloud / AI Studio | Google Cloud / AI Studio | **Google** |
| **Model Identifier** | `gemini-3.1-flash-lite` | `gemini-3.1-flash-lite` | **`gemini-3.1-flash-lite`** |
| **Total Invocations** | 11 calls | 0 calls (Tiers 1–5 resolved 100%) | **11 calls** |
| **Input Tokens (Prompt + Image)** | 18,649 tokens | 0 tokens | **18,649 tokens** |
| **Output Tokens (Structured JSON)** | 6,181 tokens | 0 tokens | **6,181 tokens** |
| **Total Tokens** | 24,830 tokens | 0 tokens | **24,830 tokens** |
| **Average Tokens Per Request (518 cases)** | 47.93 tokens/request | 0 tokens/request | **47.93 tokens/request** |
| **Measured Runtime Latency** | 68.3 seconds total (avg 6.2s/call) | N/A | **68.3 seconds** |
| **Cache Hit Latency (post-run)** | < 1 ms | N/A | **< 1 ms** |
| **Input Cost Rate ($ / 1M tokens)** | $0.075 | $0.075 | $0.075 |
| **Output Cost Rate ($ / 1M tokens)** | $0.30 | $0.30 | $0.30 |
| **Total Measured Run Cost** | **$0.003253 USD** | **$0.000000 USD** | **$0.003253 USD** |
| **Average Cost Per Request (518 cases)** | **$0.00000628 USD** | **$0.00000000 USD** | **$0.00000628 USD** |

---

## 3. Per-Screenshot Breakdown

| Evidence File ID | File Name | Captured Records | Input Tokens | Output Tokens | Latency (s) | Cost (USD) |
|---|---|---|---|---|---|---|
| `evidence_04` | `account_admin_console_20260926.png` | 4 records | 1,695 | 542 | 3.20s | $0.000290 |
| `evidence_19` | `analytics_profile_view_20260713.png` | 6 records | 1,695 | 688 | 3.04s | $0.000334 |
| `evidence_32` | `backup_restore_console_20260429.png` | 4 records | 1,695 | 511 | 3.09s | $0.000280 |
| `evidence_14` | `connector_management_console_20260807.png` | 4 records | 1,695 | 536 | 3.83s | $0.000288 |
| `evidence_23` | `customer_export_console_20260618.png` | 4 records | 1,695 | 506 | 3.15s | $0.000279 |
| `evidence_42` | `deleted_account_reference_20260310.png` | 1 record | 1,695 | 215 | 8.20s | $0.000192 |
| `evidence_60` | `marketing_profile_console.png` | 1 record | 1,695 | 224 | 14.41s | $0.000194 |
| `evidence_46` | `object_storage_browser_20260213.png` | 8 records | 1,695 | 884 | 6.73s | $0.000392 |
| `evidence_09` | `search_index_inspector_20260901.png` | 2 records | 1,695 | 398 | 18.31s | $0.000247 |
| `evidence_37` | `security_audit_explorer_20260905.png` | 6 records | 1,695 | 711 | 3.34s | $0.000340 |
| `evidence_28` | `support_ticket_console_20260524.png` | 2 records | 1,699 | 966 | 7.67s | $0.000417 |
| **Total** | *11 files* | **42 records** | **18,649** | **6,181** | **75.67s** | **$0.003253** |

---

## 4. Telemetry Integrity & Security Invariants

- **Zero Secret Ingestion:** No API keys, credentials, or session cookies are logged in telemetry files or error traces.
- **Fail-Loud Guarantee:** If model credentials are not configured, `LLMClient` immediately raises an explicit `RuntimeError` rather than silently degrading to synthetic completions.
- **Strict Deduplication & Replay:** Disk cache keyed by SHA-256 prevents redundant network round-trips; cached hits record telemetry with 0 token charge and `< 1 ms` latency.
