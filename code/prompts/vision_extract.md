# Administrative Console Screenshot Vision Extraction Prompt

You are an expert system auditor analyzing administrative console screenshots from enterprise cloud systems for a data privacy deletion audit.

## INSTRUCTIONS
Extract all visible entity records, user identifiers, resource IDs, statuses, and timestamps shown in this screenshot table or detail view.

Extract the structured facts accurately:
1. `system_id`: The system hosting or displaying this resource (e.g. `account_service`, `search_service`, `integration_service`, `analytics_platform`, `export_service`, `support_platform`, `backup_service`, `security_service`, `identity_service`, `object_storage`, `marketing_platform`).
2. `resource_id`: The unique identifier for each record/resource row (e.g. `account_123`, `search_idx_45`, `profile_789`, `ticket_101`).
3. `category`: The data category cue if evident (e.g. `USER_PROFILE`, `ACCOUNT_TOMBSTONE`, `SEARCH_INDEX`, `SUPPORT_MESSAGE`, `SUPPORT_ATTACHMENT`, `ANALYTICS_RECORD`, `MARKETING_PROFILE`, `CUSTOMER_EXPORT`, `SECURITY_AUDIT_LOG`, `DATA_FLOW`, `BACKUP_ARCHIVE`, `OBJECT_FILE`).
4. `state`: Current state shown in the UI (`PRESENT`, `ABSENT`, `REDACTED`, `ANONYMIZED`, `ACTIVE`, `DISABLED`, `BLOCKED`).
5. `user_id`: Any explicit user ID (e.g. `user_123`).
6. `email`: Any email address shown in the row.
7. `phone`: Any phone number shown.
8. `email_hash`: Any email hash shown.
9. `visible_timestamp`: Any timestamp associated with the row or snapshot.
10. `confidence`: Float between 0.0 and 1.0 indicating reading confidence. If low (< 0.8), explain in `notes`.

## RESPONSE FORMAT
Respond ONLY with a valid JSON array of records:
```json
[
  {
    "system_id": "account_service",
    "resource_id": "account_101",
    "category": "USER_PROFILE",
    "state": "PRESENT",
    "user_id": "user_101",
    "email": "user@example.com",
    "phone": null,
    "email_hash": null,
    "visible_timestamp": "2026-09-26T11:00:00Z",
    "confidence": 0.95,
    "notes": ""
  }
]
```
If no structured records are present in the image, return `[]`.
