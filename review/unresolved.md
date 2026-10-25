# Unresolved Resource States Log (Patch P3)

This log records resources whose point-in-time state at `audit_at` could not be definitively resolved from direct post-workflow observations or authoritative covering stores, falling back to deterministic safe defaults per Patch P3 (preserving earlier admissible observations or safe presence, never inventing absence).

- Case `case_34`: Resource `account_service/account_5762` — No newer evidence post-dating 2026-09-26T02:00:00Z resolves state; falling back to last admissible observation from 2026-09-15T11:54:30Z
- Case `case_34`: Resource `security_service/audit_record_3753` — No newer evidence post-dating 2026-09-26T02:00:00Z resolves state; falling back to last admissible observation from 2026-09-15T11:54:47Z
- Case `case_46`: Resource `identity_service/tombstone_17` — No direct observation or covering snapshot found in admissible view for identity_service
