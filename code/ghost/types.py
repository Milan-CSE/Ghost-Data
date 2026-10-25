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
