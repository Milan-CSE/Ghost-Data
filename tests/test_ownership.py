"""Focused unit tests for OwnershipLinker (ownership.py)."""
import hashlib
import pytest
from ghost.types import Fact, State, IdentityBag, Case, OwnedResource
from ghost.ledger import View
from ghost.ownership import OwnershipLinker
from ghost.adapters import sqlite_dump


def test_ownership_exact_identifier_match(tmp_path):
    """Test that resources matching search_surface identifiers in view are linked."""
    facts = [
        Fact(
            file_id="ev_01",
            captured_at="2026-09-01T10:00:00Z",
            system_id="account_service",
            resource_id="account_101",
            category="USER_PROFILE",
            state=State.PRESENT,
            emails=frozenset(["alice@example.com"]),
        ),
        Fact(
            file_id="ev_02",
            captured_at="2026-09-01T10:00:00Z",
            system_id="search_service",
            resource_id="search_202",
            category="SEARCH_INDEX_ENTRY",
            state=State.PRESENT,
            user_ids=frozenset(["user_99"]),
        ),
    ]
    view = View(audit_at="2026-09-02T10:00:00Z", facts=facts)
    bag = IdentityBag(
        user_id="user_99",
        active_at_audit={"email": "alice@example.com"},
        search_surface=frozenset(["alice@example.com", "user_99"]),
    )
    case = Case(
        case_id="case_t1",
        email="alice@example.com",
        requested_at="2026-08-30T10:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-08-31T10:00:00Z",
        audit_at="2026-09-02T10:00:00Z",
        request_text="Delete my data",
    )

    empty_act = tmp_path / "act.csv"
    empty_act.write_text("activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n")
    linker = OwnershipLinker(empty_act)

    owned = linker.link(case, bag, view)
    res_keys = [(r.system_id, r.resource_id) for r in owned]

    assert ("account_service", "account_101") in res_keys
    assert ("search_service", "search_202") in res_keys
    assert len(owned) == 2


def test_ownership_decoy_rejection(tmp_path):
    """Test that decoy records with similar but unmatching identifiers are rejected."""
    facts = [
        Fact(
            file_id="ev_01",
            captured_at="2026-09-01T10:00:00Z",
            system_id="account_service",
            resource_id="account_target",
            category="USER_PROFILE",
            state=State.PRESENT,
            emails=frozenset(["jonas.berg@example.com"]),
        ),
        Fact(
            file_id="ev_01",
            captured_at="2026-09-01T10:00:00Z",
            system_id="account_service",
            resource_id="account_decoy_1",
            category="USER_PROFILE",
            state=State.PRESENT,
            emails=frozenset(["jonas.berglund@example.com"]),  # Decoy name prefix
        ),
        Fact(
            file_id="ev_01",
            captured_at="2026-09-01T10:00:00Z",
            system_id="account_service",
            resource_id="account_decoy_2",
            category="USER_PROFILE",
            state=State.PRESENT,
            emails=frozenset(["joana.berg@example.com"]),  # Decoy typo
        ),
    ]
    view = View(audit_at="2026-09-02T10:00:00Z", facts=facts)
    bag = IdentityBag(
        user_id="user_jb",
        active_at_audit={"email": "jonas.berg@example.com"},
        search_surface=frozenset(["jonas.berg@example.com", "user_jb"]),
    )
    case = Case(
        case_id="case_decoy",
        email="jonas.berg@example.com",
        requested_at="2026-08-30T10:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-08-31T10:00:00Z",
        audit_at="2026-09-02T10:00:00Z",
        request_text="Delete my data",
    )

    empty_act = tmp_path / "act.csv"
    empty_act.write_text("activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n")
    linker = OwnershipLinker(empty_act)

    owned = linker.link(case, bag, view)
    res_ids = [r.resource_id for r in owned]

    assert res_ids == ["account_target"]
    assert "account_decoy_1" not in res_ids
    assert "account_decoy_2" not in res_ids


def test_ownership_relational_link(tmp_path):
    """Test linking via LINK_RESOURCE_IDENTITY in activity log."""
    act_file = tmp_path / "act.csv"
    act_file.write_text(
        "activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n"
        "act_4001,2026-09-01T06:07:01Z,LINK_RESOURCE_IDENTITY,data_catalog,search_service,search_428,SUCCESS,Data catalog linked search_428 (search_428) to g.silva76@gmail.com and user_13.\n"
    )
    linker = OwnershipLinker(act_file)
    view = View(audit_at="2026-09-02T10:00:00Z", facts=[])
    bag = IdentityBag(
        user_id="user_13",
        active_at_audit={"email": "g.silva76@gmail.com"},
        search_surface=frozenset(["g.silva76@gmail.com", "user_13"]),
    )
    case = Case(
        case_id="case_rel",
        email="g.silva76@gmail.com",
        requested_at="2026-08-30T10:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-08-31T10:00:00Z",
        audit_at="2026-09-02T10:00:00Z",
        request_text="Delete my data",
    )

    owned = linker.link(case, bag, view)
    assert len(owned) == 1
    assert owned[0].system_id == "search_service"
    assert owned[0].resource_id == "search_428"
    assert owned[0].signal == "relational"
    assert owned[0].corroborated_by == ("act_4001",)


def test_ownership_activity_corroboration_within_intake_window(tmp_path):
    """Patch P6: Test that deletion_worker activity within [requested_at, reported_at]

    corroborates resources already identified in evidence, but events outside are excluded.
    """
    act_file = tmp_path / "act.csv"
    act_file.write_text(
        "activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n"
        "act_within,2026-08-20T12:00:00Z,DELETE_RECORD,deletion_worker,account_service,account_001,SUCCESS,Target: account_001\n"
        "act_post_reported,2026-08-20T17:00:00Z,DELETE_RECORD,deletion_worker,account_service,account_001,SUCCESS,Target: account_001\n"
    )
    linker = OwnershipLinker(act_file)
    fact = Fact(
        file_id="ev_01",
        captured_at="2026-08-15T10:00:00Z",
        system_id="account_service",
        resource_id="account_001",
        category="USER_PROFILE",
        state=State.PRESENT,
        emails=frozenset(["user@example.com"]),
    )
    view = View(audit_at="2026-09-03T11:30:00Z", facts=[fact])
    bag = IdentityBag(
        user_id="user_01",
        active_at_audit={"email": "user@example.com"},
        search_surface=frozenset(["user@example.com", "user_01"]),
    )
    case = Case(
        case_id="case_01",
        email="user@example.com",
        requested_at="2026-08-18T09:14:00Z",
        reported_status="COMPLETE",
        reported_at="2026-08-20T16:42:00Z",
        audit_at="2026-09-03T11:30:00Z",
        request_text="Close account",
    )

    owned = linker.link(case, bag, view)
    assert len(owned) == 1
    assert owned[0].resource_id == "account_001"
    assert owned[0].corroborated_by == ("act_within",)
    assert "act_post_reported" not in owned[0].corroborated_by


def test_ownership_activity_alone_does_not_establish_primary_ownership(tmp_path):
    """Patch P6: Unbacked activity with no grounded evidence or relational catalog link

    must never create or establish an owned resource.
    """
    act_file = tmp_path / "act.csv"
    act_file.write_text(
        "activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n"
        "act_unbacked,2026-08-20T12:00:00Z,DELETE_RECORD,deletion_worker,account_service,account_ungrounded,SUCCESS,Target: account_ungrounded\n"
    )
    linker = OwnershipLinker(act_file)
    view = View(audit_at="2026-09-03T11:30:00Z", facts=[])  # No grounded evidence facts
    bag = IdentityBag(
        user_id="user_01",
        active_at_audit={"email": "user@example.com"},
        search_surface=frozenset(["user@example.com", "user_01"]),
    )
    case = Case(
        case_id="case_01",
        email="user@example.com",
        requested_at="2026-08-18T09:14:00Z",
        reported_status="COMPLETE",
        reported_at="2026-08-20T16:42:00Z",
        audit_at="2026-09-03T11:30:00Z",
        request_text="Close account",
    )

    owned = linker.link(case, bag, view)
    # Activity alone must not establish ownership
    assert len(owned) == 0


def test_source_resource_schema_links_primary_account_and_activity_only_corroborates(tmp_path):
    """A subject-matched row's explicit source_resource_id grounds its source account."""
    sql = tmp_path / "search.sql"
    sql.write_text(
        "CREATE TABLE search_documents_primary (resource_id TEXT, email TEXT, source_resource_id TEXT);\n"
        "INSERT INTO search_documents_primary VALUES ('search_1', 'user@example.com', 'account_1');\n",
        encoding="utf-8",
    )
    fact = sqlite_dump.parse(sql, "ev_search", "2026-09-01T12:00:00Z")[0]
    assert fact.related_resource_ids == frozenset({"account_1"})

    act_file = tmp_path / "act.csv"
    act_file.write_text(
        "activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n"
        "act_account,2026-08-20T12:00:00Z,DELETE_RECORD,deletion_worker,account_service,account_1,SUCCESS,Target: account_1\n",
        encoding="utf-8",
    )
    linker = OwnershipLinker(act_file)
    coverage = Fact(
        file_id="ev_account_snapshot", captured_at="2026-09-02T00:00:00Z",
        system_id="account_service", resource_id="account_placeholder",
        category="USER_PROFILE", state=State.PRESENT, covers_system=True,
    )
    view = View("2026-09-03T00:00:00Z", [fact, coverage])
    email_hash = hashlib.sha256(b"user@example.com").hexdigest()
    bag = IdentityBag("user_1", {"email": "user@example.com"}, frozenset({"user_1", "user@example.com", email_hash}))
    case = Case("case_rel_account", "user@example.com", "2026-08-19T00:00:00Z", "COMPLETE", "2026-08-21T00:00:00Z", "2026-09-03T00:00:00Z", "Delete my account")

    owned = linker.link(case, bag, view)
    linked = next(r for r in owned if r.resource_id == "account_1")
    assert linked.system_id == "account_service"
    assert linked.signal == "relational"
    assert linked.corroborated_by == ("act_account",)


def test_source_resource_relationship_rejects_shared_ambiguous_subjects(tmp_path):
    """A shared lookup record cannot assign its source account to concurrent subjects."""
    act_file = tmp_path / "act.csv"
    act_file.write_text(
        "activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n"
        "act_a,2026-08-20T12:00:00Z,DELETE_RECORD,deletion_worker,account_service,account_shared,SUCCESS,Target: account_shared\n"
        "act_b,2026-08-20T12:00:00Z,DELETE_RECORD,deletion_worker,account_service,account_shared,SUCCESS,Target: account_shared\n",
        encoding="utf-8",
    )
    linker = OwnershipLinker(act_file)
    shared = Fact(
        file_id="ev_shared", captured_at="2026-08-19T00:00:00Z",
        system_id="search_service", resource_id="search_shared",
        category="SEARCH_INDEX_ENTRY", state=State.PRESENT,
        emails=frozenset({"a@example.com", "b@example.com"}),
        related_resource_ids=frozenset({"account_shared"}),
    )
    view = View("2026-09-03T00:00:00Z", [shared])
    cases = [
        (Case("case_a", "a@example.com", "2026-08-19T00:00:00Z", "COMPLETE", "2026-08-21T00:00:00Z", "2026-09-03T00:00:00Z", "Delete"), IdentityBag("user_a", {}, frozenset({"user_a", "a@example.com"}))),
        (Case("case_b", "b@example.com", "2026-08-19T00:00:00Z", "COMPLETE", "2026-08-21T00:00:00Z", "2026-09-03T00:00:00Z", "Delete"), IdentityBag("user_b", {}, frozenset({"user_b", "b@example.com"}))),
    ]

    for case, bag in cases:
        assert all(r.resource_id != "account_shared" for r in linker.link(case, bag, view))


def test_source_resource_relationship_rejects_account_owned_by_another_user(tmp_path):
    act_file = tmp_path / "act.csv"
    act_file.write_text("activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n", encoding="utf-8")
    linker = OwnershipLinker(act_file)
    search = Fact(
        file_id="ev_search", captured_at="2026-08-19T00:00:00Z",
        system_id="search_service", resource_id="search_1",
        category="SEARCH_INDEX_ENTRY", state=State.PRESENT,
        emails=frozenset({"user@example.com"}),
        related_resource_ids=frozenset({"account_1"}),
    )
    other_owner = Fact(
        file_id="ev_account", captured_at="2026-08-19T00:00:00Z",
        system_id="account_service", resource_id="account_1",
        category="USER_PROFILE", state=State.PRESENT,
        emails=frozenset({"other@example.com"}),
    )
    view = View("2026-09-03T00:00:00Z", [search, other_owner])
    bag = IdentityBag("user_1", {}, frozenset({"user_1", "user@example.com"}))
    case = Case("case_owner", "user@example.com", "2026-08-18T00:00:00Z", "COMPLETE", "2026-08-20T00:00:00Z", "2026-09-03T00:00:00Z", "Delete my data")

    assert all(r.resource_id != "account_1" for r in linker.link(case, bag, view))


def test_ownership_preserves_legitimate_shared_resources(tmp_path):
    """Test that legitimate shared resources (e.g. shared support message) are preserved across subjects."""
    empty_act = tmp_path / "act.csv"
    empty_act.write_text("activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n")
    linker = OwnershipLinker(empty_act)

    shared_fact = Fact(
        file_id="ev_shared",
        captured_at="2026-08-15T10:00:00Z",
        system_id="support_platform",
        resource_id="support_shared_thread",
        category="SUPPORT_MESSAGE",
        state=State.PRESENT,
        emails=frozenset(["userA@example.com", "userB@example.com"]),
    )
    view = View(audit_at="2026-09-03T11:30:00Z", facts=[shared_fact])

    bag_a = IdentityBag(user_id="user_A", active_at_audit={"email": "userA@example.com"}, search_surface=frozenset(["userA@example.com", "user_A"]))
    bag_b = IdentityBag(user_id="user_B", active_at_audit={"email": "userB@example.com"}, search_surface=frozenset(["userB@example.com", "user_B"]))

    case_a = Case("case_A", "userA@example.com", "2026-08-18T09:00:00Z", "COMPLETE", "2026-08-20T09:00:00Z", "2026-09-03T11:30:00Z", "text")
    case_b = Case("case_B", "userB@example.com", "2026-08-19T09:00:00Z", "COMPLETE", "2026-08-21T09:00:00Z", "2026-09-03T11:30:00Z", "text")

    owned_a = linker.link(case_a, bag_a, view)
    owned_b = linker.link(case_b, bag_b, view)

    assert any(r.resource_id == "support_shared_thread" for r in owned_a)
    assert any(r.resource_id == "support_shared_thread" for r in owned_b)
