# Unresolved Resource States Log (Patch P3)

This log records resources whose point-in-time state at `audit_at` could not be definitively resolved from direct post-workflow observations or authoritative covering stores, falling back to deterministic safe defaults per Patch P3 (preserving earlier admissible observations or safe presence, never inventing absence).

- Case `case_33`: Resource `export_service/export_1260` — No newer evidence post-dating 2026-07-18T02:00:00Z resolves state; falling back to last admissible observation from 2026-06-18T12:00:00Z
- Case `case_34`: Resource `security_service/audit_record_3753` — No newer evidence post-dating 2026-09-26T02:00:00Z resolves state; falling back to last admissible observation from 2026-09-15T11:54:47Z
- Case `case_34`: Resource `support_platform/support_9538` — No newer evidence post-dating 2026-09-26T02:00:00Z resolves state; falling back to last admissible observation from 2026-09-15T11:51:46Z
