"""Focused unit tests for OwnershipLinker (ownership.py)."""
import pytest
from ghost.types import Fact, State, IdentityBag, Case, OwnedResource
from ghost.ledger import View
from ghost.ownership import OwnershipLinker


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


def test_ownership_account_activity_corroboration(tmp_path):
    """Test corroborating account profile from deletion_worker when absent from evidence."""
    act_file = tmp_path / "act.csv"
    act_file.write_text(
        "activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n"
        "act_3342,2026-08-20T16:41:43Z,DELETE_RECORD,deletion_worker,account_service,account_001,SUCCESS,Target resource: account_001.\n"
        "act_9999,2026-08-25T10:00:00Z,DELETE_RECORD,deletion_worker,account_service,account_unrelated,SUCCESS,Target resource: account_unrelated.\n"
    )
    linker = OwnershipLinker(act_file)
    view = View(audit_at="2026-09-03T11:30:00Z", facts=[])
    bag = IdentityBag(
        user_id="user_01",
        active_at_audit={"email": "amina.elmasri@gmail.com"},
        search_surface=frozenset(["amina.elmasri@gmail.com", "user_01"]),
    )
    case = Case(
        case_id="case_01",
        email="amina.elmasri@gmail.com",
        requested_at="2026-08-18T09:14:00Z",
        reported_status="COMPLETE",
        reported_at="2026-08-20T16:42:00Z",  # event 17s prior
        audit_at="2026-09-03T11:30:00Z",
        request_text="Close account",
    )

    owned = linker.link(case, bag, view)
    assert len(owned) == 1
    assert owned[0].system_id == "account_service"
    assert owned[0].resource_id == "account_001"
    assert owned[0].signal == "activity_corroboration"
    assert owned[0].corroborated_by == ("act_3342",)
