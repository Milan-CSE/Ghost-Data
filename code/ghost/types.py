"""Core types for ghost data deletion audit."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class Case:
    case_id: str
    email: str
    requested_at: str
    reported_status: str
    reported_at: str
    audit_at: str
    request_text: str


@dataclass(frozen=True)
class Intent:
    """Arbitrated deletion intent result."""
    decision: str  # "DELETION" or "NOT_APPLICABLE"
    tier: int      # 1 to 6
    reason: str
    confidence: float = 1.0

    @property
    def is_not_deletion(self) -> bool:
        return self.decision == "NOT_APPLICABLE"

    @property
    def is_deletion(self) -> bool:
        return self.decision == "DELETION"


@dataclass(frozen=True)
class Fact:
    """One normalized observation."""
    file_id: str
    captured_at: str
    system_id: str
    resource_id: str
    category: str
    state: State
    emails: frozenset[str] = field(default_factory=frozenset)
    hashes: frozenset[str] = field(default_factory=frozenset)
    user_ids: frozenset[str] = field(default_factory=frozenset)
    phones: frozenset[str] = field(default_factory=frozenset)
    store: str = ""  # e.g. "primary", "failover_replica", "bundle"
    covers_system: bool = False  # True only for authoritative full-table/bundle observations
    file_captured_at: str = ""  # Manifest captured_at of the evidence file


VALID_SYSTEMS: frozenset[str] = frozenset({
    "account_service",
    "analytics_platform",
    "backup_service",
    "export_service",
    "identity_service",
    "integration_service",
    "search_service",
    "security_service",
    "support_platform",
})


@dataclass(frozen=True)
class IdentityBag:
    user_id: str
    active_at_audit: dict  # email, phone, email_hash valid at audit_at
    search_surface: frozenset[str]  # all identifiers valid at or before audit_at (+ hashes)


@dataclass(frozen=True)
class OwnedResource:
    system_id: str
    resource_id: str
    category: str
    signal: str  # "identifier" | "relational" | "trace" | "vision"
    corroborated_by: tuple[str, ...] = ()  # activity_ids


@dataclass(frozen=True)
class ResourceState:
    system_id: str
    resource_id: str
    category: str
    state: State
    evidence_id: str
    is_unresolved: bool = False
    details: str = ""


def normalize_system_id(resource_id: str, system_hint: str = "") -> str:
    """Deterministically map resource_id and system_hint to authoritative system_id."""
    res = resource_id.strip(' \t\n\r"\'\\').lower() if resource_id else ""
    if res.startswith("account_"):
        return "account_service"
    if res.startswith("search_"):
        return "search_service"
    if res.startswith("support_"):
        return "support_platform"
    if res.startswith("export_"):
        return "export_service"
    if res.startswith("backup_"):
        return "backup_service"
    if res.startswith("data_flow_"):
        return "integration_service"
    if res.startswith("analytics_"):
        return "analytics_platform"
    if res.startswith("audit_") or res.startswith("audit_record_"):
        return "security_service"
    if res.startswith("tombstone_"):
        return "identity_service"
    if res.startswith("marketing_"):
        return "marketing_platform"
    if res.startswith("email_"):
        return "email_service"
    if res.startswith("cache_"):
        return "cache_service"
    if res.startswith("legal_hold_") or res.startswith("legal_"):
        return "legal_service"

    hint = (system_hint or "").strip().lower()
    if "support" in hint:
        return "support_platform"
    if "account" in hint:
        return "account_service"
    if "search" in hint:
        return "search_service"
    if "analytics" in hint:
        return "analytics_platform"
    if "export" in hint:
        return "export_service"
    if "backup" in hint:
        return "backup_service"
    if "integration" in hint or "connector" in hint or "flow" in hint:
        return "integration_service"
    if "security" in hint or "audit" in hint:
        return "security_service"
    if "identity" in hint or "tombstone" in hint:
        return "identity_service"
    if "legal" in hint:
        return "legal_service"
    if "marketing" in hint:
        return "marketing_platform"

    return system_hint or "account_service"


def infer_category(resource_id: str, system_id: str = "", collection_hint: str = "") -> str:
    """Infer the data category from collection/schema hints, resource prefix, or system_id."""
    hint = (collection_hint or "").strip().lower()
    res = (resource_id or "").strip(' \t\n\r"\'\\').lower()

    if "ticket_attachment" in hint or "attachment" in hint or "attachment" in res:
        return "SUPPORT_ATTACHMENT"
    if "conversation" in hint or "support_record" in hint or "support_message" in hint:
        return "SUPPORT_MESSAGE"
    if "security_audit" in hint or "audit_record" in res or res.startswith("audit_"):
        return "SECURITY_AUDIT_LOG"
    if "deleted_customer_reference" in hint or "tombstone" in hint or res.startswith("tombstone_"):
        return "ACCOUNT_TOMBSTONE"
    if "analytics" in hint or res.startswith("analytics_"):
        return "ANALYTICS_PROFILE"
    if "search" in hint or res.startswith("search_"):
        return "SEARCH_INDEX_ENTRY"
    if "export" in hint or res.startswith("export_"):
        return "USER_EXPORT"
    if "backup" in hint or res.startswith("backup_"):
        return "BACKUP_ARCHIVE"
    if "connector" in hint or res.startswith("data_flow_"):
        return "DATA_FLOW"
    if "retained_order" in hint or "legal_hold" in hint or res.startswith("legal_"):
        return "LEGAL_HOLD_RECORD"
    if "marketing" in hint or res.startswith("marketing_"):
        return "MARKETING_PROFILE"
    if "cache" in hint or res.startswith("cache_"):
        return "CACHE_ENTRY"
    if "secondary" in hint or res.startswith("secondary_"):
        return "SECONDARY_IDENTIFIER"
    if "email_log" in hint or res.startswith("email_"):
        return "EMAIL_DELIVERY_LOG"
    if "telemetry" in hint or res.startswith("telemetry_"):
        return "PRODUCT_TELEMETRY"

    norm_sys = normalize_system_id(resource_id, system_id)
    if norm_sys == "account_service":
        return "USER_PROFILE"
    if norm_sys == "support_platform":
        return "SUPPORT_MESSAGE"
    if norm_sys == "analytics_platform":
        return "ANALYTICS_PROFILE"
    if norm_sys == "search_service":
        return "SEARCH_INDEX_ENTRY"
    if norm_sys == "security_service":
        return "SECURITY_AUDIT_LOG"
    if norm_sys == "export_service":
        return "USER_EXPORT"
    if norm_sys == "backup_service":
        return "BACKUP_ARCHIVE"
    if norm_sys == "integration_service":
        return "DATA_FLOW"
    if norm_sys == "identity_service":
        return "ACCOUNT_TOMBSTONE"

    return "USER_PROFILE"


_EMAIL_REGEX = None
_USER_ID_REGEX = None
_HEX64_REGEX = None


def _get_regexes():
    global _EMAIL_REGEX, _USER_ID_REGEX, _HEX64_REGEX
    if _EMAIL_REGEX is None:
        import re
        _EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
        _USER_ID_REGEX = re.compile(r"\buser_\d+\b")
        _HEX64_REGEX = re.compile(r"\b[a-fA-F0-9]{64}\b")
    return _EMAIL_REGEX, _USER_ID_REGEX, _HEX64_REGEX


def extract_identifiers_from_obj(obj: Any) -> tuple[set[str], set[str], set[str], set[str]]:
    """Recursively extract (emails, hashes, user_ids, phones) from any dict/list/value structure."""
    import hashlib
    email_re, uid_re, hex_re = _get_regexes()

    emails: set[str] = set()
    hashes: set[str] = set()
    user_ids: set[str] = set()
    phones: set[str] = set()

    def sha(t: str) -> str:
        return hashlib.sha256(t.strip().lower().encode("utf-8")).hexdigest()

    def traverse(item: Any):
        if isinstance(item, dict):
            for k, v in item.items():
                if v is None:
                    continue
                k_lower = str(k).lower()
                v_str = str(v).strip()
                if not v_str or v_str.lower() == "null":
                    continue

                if ("email_hash" in k_lower or "correlation" in k_lower or "hash" in k_lower or "key" in k_lower) and hex_re.match(v_str):
                    hashes.add(v_str.lower())
                elif hex_re.match(v_str):
                    hashes.add(v_str.lower())
                elif any(x in k_lower for x in ["email", "selector", "uploaded_by"]):
                    for em in email_re.findall(v_str):
                        em_clean = em.strip()
                        emails.add(em_clean)
                        emails.add(em_clean.lower())
                        hashes.add(sha(em_clean))
                elif "phone" in k_lower:
                    norm_p = "".join(c for c in v_str if c.isdigit() or c == "+")
                    if norm_p:
                        phones.add(norm_p)
                elif any(x in k_lower for x in ["user", "reference", "subject", "customer"]):
                    if "@" in v_str:
                        for em in email_re.findall(v_str):
                            em_clean = em.strip()
                            emails.add(em_clean)
                            emails.add(em_clean.lower())
                            hashes.add(sha(em_clean))
                    elif v_str.startswith("user_"):
                        user_ids.add(v_str)
                    elif hex_re.match(v_str):
                        hashes.add(v_str.lower())
                traverse(v)
        elif isinstance(item, (list, tuple, set)):
            for v in item:
                traverse(v)
        elif isinstance(item, str):
            for em in email_re.findall(item):
                em_clean = em.strip()
                emails.add(em_clean)
                emails.add(em_clean.lower())
                hashes.add(sha(em_clean))
            for uid in uid_re.findall(item):
                user_ids.add(uid)

    traverse(obj)
    return emails, hashes, user_ids, phones


