"""Focused unit tests for StateReconstructor (state.py)."""
import pytest
from pathlib import Path
from ghost.types import Fact, State, OwnedResource, Case
from ghost.ledger import View
from ghost.state import StateReconstructor


def test_state_exact_cutoff_and_post_cutoff_exclusion():
    """Test that captured_at == audit_at is admitted, but captured_at > audit_at is excluded."""
    cutoff = "2026-09-12T12:00:00Z"
    facts = [
        Fact(
            file_id="ev_admissible",
            captured_at="2026-09-12T12:00:00Z",  # Exactly at cutoff
            system_id="search_service",
            resource_id="search_101",
            category="SEARCH_INDEX_ENTRY",
            state=State.PRESENT,
        ),
        Fact(
            file_id="ev_post_cutoff",
            captured_at="2026-09-12T12:00:01Z",  # 1 second after cutoff
            system_id="search_service",
            resource_id="search_101",
            category="SEARCH_INDEX_ENTRY",
            state=State.ABSENT,
        ),
    ]
    # View filters out post-cutoff facts
    view = View(audit_at=cutoff, facts=facts)
    owned = OwnedResource("search_service", "search_101", "SEARCH_INDEX_ENTRY", "identifier")
    case = Case("c1", "test@example.com", "2026-09-10T10:00:00Z", "COMPLETE", "2026-09-11T10:00:00Z", cutoff, "text")

    recon = StateReconstructor()
    res_state = recon.reconstruct(owned, view, case)

    assert res_state.state == State.PRESENT
    assert res_state.evidence_id == "ev_admissible"


def test_state_replica_drift_detection():
    """Test that if an operational failover replica retains a record, it takes precedence."""
    cutoff = "2026-09-10T12:00:00Z"
    facts = [
        Fact(
            file_id="ev_primary",
            captured_at=cutoff,
            system_id="account_service",
            resource_id="account_drift",
            category="USER_PROFILE",
            state=State.ABSENT,
            store="primary_db",
        ),
        Fact(
            file_id="ev_failover",
            captured_at=cutoff,
            system_id="account_service",
            resource_id="account_drift",
            category="USER_PROFILE",
            state=State.PRESENT,
            store="failover_replica",
        ),
    ]
    view = View(audit_at=cutoff, facts=facts)
    owned = OwnedResource("account_service", "account_drift", "USER_PROFILE", "identifier")
    case = Case("c2", "test@example.com", "2026-09-08T10:00:00Z", "COMPLETE", "2026-09-09T10:00:00Z", cutoff, "text")

    recon = StateReconstructor()
    res_state = recon.reconstruct(owned, view, case)

    assert res_state.state == State.PRESENT
    assert res_state.evidence_id == "ev_failover"


def test_state_covering_store_omission_absence():
    """Test that a resource omitted from an authoritative covering store is resolved as ABSENT."""
    cutoff = "2026-09-15T12:00:00Z"
    facts = [
        Fact(
            file_id="ev_covering_bundle",
            captured_at=cutoff,
            system_id="account_service",
            resource_id="other_account_99",
            category="USER_PROFILE",
            state=State.PRESENT,
            covers_system=True,  # Authoritative covering store
        )
    ]
    view = View(audit_at=cutoff, facts=facts)
    owned = OwnedResource("account_service", "account_absent_target", "USER_PROFILE", "activity_corroboration")
    case = Case("c3", "test@example.com", "2026-09-10T10:00:00Z", "COMPLETE", "2026-09-11T10:00:00Z", cutoff, "text")

    recon = StateReconstructor()
    res_state = recon.reconstruct(owned, view, case)

    assert res_state.state == State.ABSENT
    assert res_state.evidence_id == "ev_covering_bundle"
    assert res_state.is_unresolved is False


def test_state_process_predicates():
    """Test process states for integration_service and backup_service."""
    cutoff = "2026-09-15T12:00:00Z"
    facts = [
        Fact(
            file_id="ev_flow",
            captured_at=cutoff,
            system_id="integration_service",
            resource_id="data_flow_1",
            category="DATA_FLOW",
            state=State.ACTIVE,
        ),
        Fact(
            file_id="ev_backup",
            captured_at=cutoff,
            system_id="backup_service",
            resource_id="backup_1",
            category="BACKUP_ARCHIVE",
            state=State.BLOCKED,
        ),
    ]
    view = View(audit_at=cutoff, facts=facts)
    case = Case("c4", "test@example.com", "2026-09-10T10:00:00Z", "COMPLETE", "2026-09-11T10:00:00Z", cutoff, "text")
    recon = StateReconstructor()

    flow_res = recon.reconstruct(OwnedResource("integration_service", "data_flow_1", "DATA_FLOW", "identifier"), view, case)
    assert flow_res.state == State.ACTIVE

    backup_res = recon.reconstruct(OwnedResource("backup_service", "backup_1", "BACKUP_ARCHIVE", "identifier"), view, case)
    assert backup_res.state == State.BLOCKED


def test_p3_last_admissible_observation_preserved(tmp_path, monkeypatch):
    """P3 Case 1: When a resource has an earlier admissible observation and no newer observation

    post-dating the workflow, preserve the last admissible observation as the fallback,
    record the uncertainty in review/unresolved.md, and mark is_unresolved=True.
    """
    monkeypatch.chdir(tmp_path)
    cutoff = "2026-09-15T12:00:00Z"
    facts = [
        Fact(
            file_id="ev_earlier_obs",
            captured_at="2026-08-15T10:00:00Z",  # Earlier observation, well before reported_at
            system_id="support_platform",
            resource_id="support_shared_conv",
            category="SUPPORT_MESSAGE",
            state=State.PRESENT,
            emails=frozenset(["user@example.com"]),
        )
    ]
    view = View(audit_at=cutoff, facts=facts)
    owned = OwnedResource("support_platform", "support_shared_conv", "SUPPORT_MESSAGE", "identifier")
    case = Case("case_p3_1", "user@example.com", "2026-08-10T10:00:00Z", "COMPLETE", "2026-08-20T10:00:00Z", cutoff, "text")

    recon = StateReconstructor()
    res_state = recon.reconstruct(owned, view, case)

    # State and evidence citation are preserved from last admissible observation
    assert res_state.state == State.PRESENT
    assert res_state.evidence_id == "ev_earlier_obs"
    # Fallback to last admissible observation must NOT be marked fully resolved
    assert res_state.is_unresolved is True

    # Must record uncertainty in review/unresolved.md
    log_file = tmp_path / "review" / "unresolved.md"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "case_p3_1" in content
    assert "support_shared_conv" in content


def test_p3_no_admissible_observation_deterministic_fallback(tmp_path, monkeypatch):
    """P3 Case 2: When a resource has no admissible observation (and no covering store),

    do not infer absence; use plan-permitted deterministic fallback, record in review/unresolved.md.
    """
    monkeypatch.chdir(tmp_path)
    view = View(audit_at="2026-09-15T12:00:00Z", facts=[])  # Empty view, no covering store
    owned_rec = OwnedResource("custom_service", "res_unobserved_record", "USER_PROFILE", "identifier")
    owned_flow = OwnedResource("integration_service", "flow_unobserved", "DATA_FLOW", "relational")
    case = Case("case_p3_2", "user@example.com", "2026-09-10T10:00:00Z", "COMPLETE", "2026-09-11T10:00:00Z", "2026-09-15T12:00:00Z", "text")

    recon = StateReconstructor()
    st_rec = recon.reconstruct(owned_rec, view, case)
    st_flow = recon.reconstruct(owned_flow, view, case)

    # Never infer absence: records default to PRESENT, flows/backups default to ACTIVE
    assert st_rec.state == State.PRESENT
    assert st_rec.is_unresolved is True
    assert st_rec.evidence_id == ""

    assert st_flow.state == State.ACTIVE
    assert st_flow.is_unresolved is True
    assert st_flow.evidence_id == ""

    # Must log uncertainty to review/unresolved.md
    log_file = tmp_path / "review" / "unresolved.md"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "res_unobserved_record" in content
    assert "flow_unobserved" in content
