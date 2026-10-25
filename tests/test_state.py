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


def test_state_unresolved_fallback(tmp_path, monkeypatch):
    """Test Patch P3 fallback and review/unresolved.md logging when state is completely ungrounded."""
    monkeypatch.chdir(tmp_path)
    view = View(audit_at="2026-09-15T12:00:00Z", facts=[])  # Empty view, no covering store
    owned = OwnedResource("custom_service", "res_mystery", "USER_PROFILE", "speculative")
    case = Case("case_mystery", "test@example.com", "2026-09-10T10:00:00Z", "COMPLETE", "2026-09-11T10:00:00Z", "2026-09-15T12:00:00Z", "text")

    recon = StateReconstructor()
    res_state = recon.reconstruct(owned, view, case)

    assert res_state.is_unresolved is True
    assert res_state.state == State.ABSENT  # Safe fallback
    assert (tmp_path / "review" / "unresolved.md").exists()
    content = (tmp_path / "review" / "unresolved.md").read_text(encoding="utf-8")
    assert "case_mystery" in content
    assert "res_mystery" in content
