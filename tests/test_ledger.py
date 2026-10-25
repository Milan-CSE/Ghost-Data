"""Unit tests for Evidence Ledger, View, and cross-format covering index (test_ledger.py)."""
from __future__ import annotations
import pytest
from ghost.ledger import Ledger, View
from ghost.types import Fact, State


def test_inclusive_temporal_filtering():
    """Verify captured_at <= audit_at is admitted, captured_at > audit_at is strictly excluded."""
    ledger = Ledger()
    f_before = Fact(
        file_id="ev_01",
        captured_at="2026-09-10T12:00:00Z",
        system_id="account_service",
        resource_id="account_100",
        category="USER_PROFILE",
        state=State.PRESENT,
    )
    f_exact = Fact(
        file_id="ev_02",
        captured_at="2026-09-12T12:00:00Z",  # exact audit_at
        system_id="account_service",
        resource_id="account_100",
        category="USER_PROFILE",
        state=State.ABSENT,
    )
    f_after = Fact(
        file_id="ev_03",
        captured_at="2026-09-12T12:00:01Z",  # 1 second after audit_at
        system_id="account_service",
        resource_id="account_100",
        category="USER_PROFILE",
        state=State.PRESENT,
    )

    ledger.add([f_before, f_exact, f_after])

    view = ledger.admissible(audit_at="2026-09-12T12:00:00Z")
    assert len(view.facts) == 2
    assert f_after not in view.facts

    latest_fact = view.latest("account_service", "account_100")
    assert latest_fact is not None
    assert latest_fact.file_id == "ev_02"
    assert latest_fact.state == State.ABSENT


def test_case_31_cross_format_covering_snapshot_selection():
    """Explicit regression test for case_31 defect.
    
    Verifies that the covering index spans across SQL dumps and JSON bundles,
    so that newer snapshot bundle evidence_51 supersedes older SQL dump evidence_54.
    """
    ledger = Ledger()

    # Older SQL dump (evidence_54)
    sql_dump_fact = Fact(
        file_id="evidence_54",
        captured_at="2026-09-02T23:00:00Z",
        system_id="account_service",
        resource_id="account_placeholder",
        category="USER_PROFILE",
        state=State.PRESENT,
        store="customer_accounts_failover_replica",
        covers_system=True,
    )

    # Newer JSON snapshot bundle (evidence_51)
    json_bundle_fact = Fact(
        file_id="evidence_51",
        captured_at="2026-09-15T12:00:00Z",
        system_id="account_service",
        resource_id="account_placeholder_2",
        category="USER_PROFILE",
        state=State.PRESENT,
        store="account_service:customer_profiles",
        covers_system=True,
    )

    ledger.add([sql_dump_fact, json_bundle_fact])

    # Case 31 audit_at is 2026-09-15T12:00:00Z
    view_case_31 = ledger.admissible(audit_at="2026-09-15T12:00:00Z")
    selected_covering = view_case_31.covering_snapshot("account_service")

    # MUST pick evidence_51 (newer JSON bundle), NOT evidence_54 (older SQL dump)
    assert selected_covering == "evidence_51"

    # If audit_at was before the JSON bundle (e.g. 2026-09-10), it should pick evidence_54
    view_earlier = ledger.admissible(audit_at="2026-09-10T00:00:00Z")
    assert view_earlier.covering_snapshot("account_service") == "evidence_54"

    # If audit_at was before any snapshot, returns None
    view_ancient = ledger.admissible(audit_at="2026-08-01T00:00:00Z")
    assert view_ancient.covering_snapshot("account_service") is None


def test_replication_drift_presence_priority():
    """When primary says ABSENT and failover replica says PRESENT at same timestamp, latest() returns PRESENT."""
    ledger = Ledger()
    t = "2026-09-05T12:00:00Z"
    primary_fact = Fact(
        file_id="ev_sql",
        captured_at=t,
        system_id="account_service",
        resource_id="account_drift",
        category="USER_PROFILE",
        state=State.ABSENT,
        store="customer_profiles_primary",
        covers_system=True,
    )
    replica_fact = Fact(
        file_id="ev_sql",
        captured_at=t,
        system_id="account_service",
        resource_id="account_drift",
        category="USER_PROFILE",
        state=State.PRESENT,
        store="customer_profiles_failover_replica",
        covers_system=True,
    )

    ledger.add([primary_fact, replica_fact])
    view = ledger.admissible(t)

    latest = view.latest("account_service", "account_drift")
    assert latest is not None
    assert latest.state == State.PRESENT


def test_by_identifier_lookup():
    """Verify lookup by email or user_id returns all linked observations."""
    ledger = Ledger()
    f1 = Fact(
        file_id="ev_1",
        captured_at="2026-09-01T10:00:00Z",
        system_id="account_service",
        resource_id="account_01",
        category="USER_PROFILE",
        state=State.PRESENT,
        emails=frozenset(["user@example.com"]),
        user_ids=frozenset(["user_50"]),
    )
    f2 = Fact(
        file_id="ev_2",
        captured_at="2026-09-02T10:00:00Z",
        system_id="support_platform",
        resource_id="support_01",
        category="SUPPORT_MESSAGE",
        state=State.PRESENT,
        emails=frozenset(["user@example.com"]),
    )

    ledger.add([f1, f2])
    view = ledger.admissible("2026-09-05T00:00:00Z")

    results_email = view.by_identifier("USER@EXAMPLE.COM")
    assert len(results_email) == 2

    results_uid = view.by_identifier("user_50")
    assert len(results_uid) == 1
    assert results_uid[0].resource_id == "account_01"
