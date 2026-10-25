"""Mandatory Synthetic Evaluation Cases (tests/test_custom_cases.py).

Implements the eight custom evaluation cases required by COMBINED_PLAN.md Part A Patch P7:
1. case_custom_01: Strict Temporal Cutoff Invariant (T <= audit_at anti-leakage)
2. case_custom_02: Operational Replica Drift Invariant (primary absent, replica present)
3. case_custom_03: Account Tombstone Direct Identifier Redaction (Rule 15 compliance)
4. case_custom_04: Uppercase and Mixed-Case Email Resolution
5. case_custom_05: Historical-Only Email Rollback / Recovery from Audit Log
6. case_custom_06: Decoy Name Rejection (Planted Lookalike / Decoy Suppression)
7. case_custom_07: Backup Restore Blocked vs Allowed Predicates
8. case_custom_08: Tombstone Dirty (PII Exposed) vs Clean
"""
import pytest
from ghost.types import Case, Fact, State, IdentityBag, OwnedResource
from ghost.ledger import Ledger, View
from ghost.identity import build_bag
from ghost.ownership import OwnershipLinker
from ghost.state import StateReconstructor
from ghost.policy import PolicyCompiler


# ---------------------------------------------------------------------------
# Case 1: Strict Temporal Cutoff Invariant
# ---------------------------------------------------------------------------
def test_case_custom_01_temporal_cutoff_exclusion():
    """Post-cutoff evidence (T > audit_at) must be strictly excluded from the View."""
    admissible_fact = Fact(
        file_id="ev_admissible",
        captured_at="2026-09-10T12:00:00Z",
        system_id="account_service",
        resource_id="acc_01",
        category="USER_PROFILE",
        state=State.ABSENT,
        user_ids=frozenset(["user_c01"]),
    )
    post_cutoff_fact = Fact(
        file_id="ev_post_cutoff_decoy",
        captured_at="2026-09-10T14:00:00Z",
        system_id="account_service",
        resource_id="acc_01",
        category="USER_PROFILE",
        state=State.PRESENT,
        user_ids=frozenset(["user_c01"]),
    )

    # View at audit_at 2026-09-10T12:00:00Z
    view = View("2026-09-10T12:00:00Z", [admissible_fact, post_cutoff_fact])
    assert len(view.facts) == 1
    assert view.facts[0].file_id == "ev_admissible"
    assert view.facts[0].state == State.ABSENT


# ---------------------------------------------------------------------------
# Case 2: Operational Replica Drift Invariant
# ---------------------------------------------------------------------------
def test_case_custom_02_operational_replica_drift(tmp_path):
    """Primary DB absence does not establish deletion if a failover replica contains surviving data."""
    facts = [
        Fact(
            file_id="ev_primary",
            captured_at="2026-09-02T10:00:00Z",
            system_id="account_service",
            resource_id="acc_02",
            category="USER_PROFILE",
            state=State.ABSENT,
            user_ids=frozenset(["user_c02"]),
        ),
        Fact(
            file_id="ev_replica",
            captured_at="2026-09-03T12:00:00Z",
            system_id="account_service",
            resource_id="acc_02",
            category="USER_PROFILE",
            state=State.PRESENT,
            user_ids=frozenset(["user_c02"]),
            store="failover_replica",
        ),
    ]
    view = View(audit_at="2026-09-03T12:00:00Z", facts=facts)
    bag = IdentityBag(
        user_id="user_c02",
        active_at_audit={"email": "c02@example.com"},
        search_surface=frozenset(["user_c02", "c02@example.com"]),
    )
    case = Case(
        case_id="case_custom_02",
        email="c02@example.com",
        requested_at="2026-09-01T08:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-09-02T12:00:00Z",
        audit_at="2026-09-03T12:00:00Z",
        request_text="Delete my account permanently",
    )

    act_file = tmp_path / "act.csv"
    act_file.write_text("activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n")
    linker = OwnershipLinker(act_file)
    owned = linker.link(case, bag, view)
    assert len(owned) == 1
    assert owned[0].resource_id == "acc_02"

    recon = StateReconstructor()
    res_state = recon.reconstruct(owned[0], view, case)
    assert res_state.state == State.PRESENT
    assert res_state.evidence_id == "ev_replica"

    compiler = PolicyCompiler()
    steps = compiler.compile_resource(res_state, is_case_complete=False)
    ops = [s.operation for s in steps]
    assert "REPORT_REMAINING_RECORD" in ops
    assert "DELETE_RECORD" in ops
    assert "VERIFY_RECORD_ABSENT" in ops


# ---------------------------------------------------------------------------
# Case 3: Account Tombstone Direct Identifier Redaction
# ---------------------------------------------------------------------------
def test_case_custom_03_tombstone_direct_identifier_redaction():
    """Preserving internal user_id is permitted for tombstones; direct PII must be redacted."""
    facts = [
        Fact(
            file_id="ev_tombstone",
            captured_at="2026-09-07T12:00:00Z",
            system_id="account_service",
            resource_id="acc_03",
            category="ACCOUNT_TOMBSTONE",
            state=State.REDACTED,
            user_ids=frozenset(["user_c03"]),
            emails=frozenset(),
            phones=frozenset(),
        )
    ]
    view = View(audit_at="2026-09-07T12:00:00Z", facts=facts)
    owned = OwnedResource(
        system_id="account_service",
        resource_id="acc_03",
        category="ACCOUNT_TOMBSTONE",
        signal="identifier",
    )
    case = Case(
        case_id="case_custom_03",
        email="c03@example.com",
        requested_at="2026-09-05T09:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-09-06T09:00:00Z",
        audit_at="2026-09-07T12:00:00Z",
        request_text="Close my account",
    )

    recon = StateReconstructor()
    res_state = recon.reconstruct(owned, view, case)
    assert res_state.state == State.REDACTED

    compiler = PolicyCompiler()
    steps = compiler.compile_resource(res_state, is_case_complete=True)
    assert len(steps) == 1
    assert steps[0].operation == "VERIFY_RECORD_REDACTED"
    assert steps[0].state == "REDACTED"
    assert steps[0].evidence_id == "ev_tombstone"


# ---------------------------------------------------------------------------
# Case 4: Uppercase and Mixed-Case Email Resolution
# ---------------------------------------------------------------------------
def test_case_custom_04_uppercase_mixed_case_email_resolution():
    """Emails differing only in case must resolve to the identical subject and search surface."""
    identities = {
        "user_c04": {
            "user_id": "user_c04",
            "name": "Devon Smith",
            "email": "devon.smith@example.com",
            "phone": "+1-555-0104",
            "email_hash": "hash04",
            "updated_at": "2026-08-01T00:00:00Z",
        }
    }
    audit_log = []

    bag = build_bag(
        {"email": "DEVON.SMITH@EXAMPLE.COM", "audit_at": "2026-09-01T00:00:00Z"},
        identities,
        audit_log,
    )
    assert bag is not None
    assert bag.user_id == "user_c04"
    assert "devon.smith@example.com" in bag.search_surface
    assert "user_c04" in bag.search_surface


# ---------------------------------------------------------------------------
# Case 5: Historical-Only Email Rollback / Recovery from Audit Log
# ---------------------------------------------------------------------------
def test_case_custom_05_historical_email_rollback_recovery():
    """A request referencing an older email must resolve via audit log without leaking post-cutoff changes."""
    identities = {
        "user_c05": {
            "user_id": "user_c05",
            "name": "Elena Rostova",
            "email": "elena.new@example.com",
            "phone": "+1-555-0105",
            "email_hash": "hash_new",
            "updated_at": "2026-08-15T00:00:00Z",
        }
    }
    audit_log = [
        {
            "audit_id": "aud_01",
            "user_id": "user_c05",
            "field_name": "email",
            "old_value": "elena.old@example.com",
            "new_value": "elena.new@example.com",
            "event_time": "2026-08-15T00:00:00Z",
        }
    ]

    # Pre-cutoff request: audit_at is 2026-08-10, prior to email change
    bag_pre = build_bag(
        {"email": "elena.old@example.com", "audit_at": "2026-08-10T00:00:00Z"},
        identities,
        audit_log,
    )
    assert bag_pre is not None
    assert bag_pre.user_id == "user_c05"
    assert bag_pre.active_at_audit["email"] == "elena.old@example.com"
    # Post-cutoff email must not be in search surface before cutoff
    assert "elena.new@example.com" not in bag_pre.search_surface

    # Post-cutoff request: audit_at is 2026-08-20, after email change
    bag_post = build_bag(
        {"email": "elena.old@example.com", "audit_at": "2026-08-20T00:00:00Z"},
        identities,
        audit_log,
    )
    assert bag_post is not None
    assert bag_post.user_id == "user_c05"
    assert "elena.old@example.com" in bag_post.search_surface
    assert "elena.new@example.com" in bag_post.search_surface


# ---------------------------------------------------------------------------
# Case 6: Decoy Name Rejection
# ---------------------------------------------------------------------------
def test_case_custom_06_decoy_name_rejection(tmp_path):
    """Resources belonging to decoys with matching names but distinct identifiers must not be linked."""
    facts = [
        Fact(
            file_id="ev_target",
            captured_at="2026-09-01T10:00:00Z",
            system_id="account_service",
            resource_id="acc_target",
            category="USER_PROFILE",
            state=State.PRESENT,
            user_ids=frozenset(["user_target"]),
        ),
        Fact(
            file_id="ev_decoy",
            captured_at="2026-09-01T10:00:00Z",
            system_id="account_service",
            resource_id="acc_decoy",
            category="USER_PROFILE",
            state=State.PRESENT,
            user_ids=frozenset(["user_decoy"]),
        ),
    ]
    view = View(audit_at="2026-09-02T10:00:00Z", facts=facts)
    bag = IdentityBag(
        user_id="user_target",
        active_at_audit={"name": "Alex Taylor", "email": "alex.taylor@example.com"},
        search_surface=frozenset(["user_target", "alex.taylor@example.com"]),
    )
    case = Case(
        case_id="case_custom_06",
        email="alex.taylor@example.com",
        requested_at="2026-08-30T10:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-08-31T10:00:00Z",
        audit_at="2026-09-02T10:00:00Z",
        request_text="Delete my data",
    )

    act_file = tmp_path / "act.csv"
    act_file.write_text("activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n")
    linker = OwnershipLinker(act_file)
    owned = linker.link(case, bag, view)

    linked_res_ids = {r.resource_id for r in owned}
    assert "acc_target" in linked_res_ids
    assert "acc_decoy" not in linked_res_ids  # Decoy rejected


# ---------------------------------------------------------------------------
# Case 7: Backup Restore Blocked vs Allowed Predicates
# ---------------------------------------------------------------------------
def test_case_custom_07_restore_blocked_vs_allowed():
    """Active restore risks require BLOCK_RESTORE; verified blocked restores pass."""
    case = Case(
        case_id="case_c07",
        email="c07@example.com",
        requested_at="2026-09-01T00:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-09-02T00:00:00Z",
        audit_at="2026-09-03T00:00:00Z",
        request_text="Delete my data",
    )
    recon = StateReconstructor()
    compiler = PolicyCompiler()

    # Sub-case A: Active restore risk
    facts_active = [
        Fact(
            file_id="ev_backup_active",
            captured_at="2026-09-02T12:00:00Z",
            system_id="backup_service",
            resource_id="backup_archive_01",
            category="BACKUP_ARCHIVE",
            state=State.ACTIVE,
            user_ids=frozenset(["user_c07"]),
        )
    ]
    view_active = View(audit_at="2026-09-03T00:00:00Z", facts=facts_active)
    owned_active = OwnedResource(
        system_id="backup_service",
        resource_id="backup_archive_01",
        category="BACKUP_ARCHIVE",
        signal="identifier",
    )
    state_a = recon.reconstruct(owned_active, view_active, case)
    steps_a = compiler.compile_resource(state_a, is_case_complete=False)
    ops_a = [s.operation for s in steps_a]
    assert "REPORT_RESTORE_RISK" in ops_a
    assert "BLOCK_RESTORE" in ops_a
    assert "VERIFY_RESTORE_BLOCKED" in ops_a

    # Sub-case B: Already blocked restore
    facts_blocked = [
        Fact(
            file_id="ev_backup_blocked",
            captured_at="2026-09-02T12:00:00Z",
            system_id="backup_service",
            resource_id="backup_archive_02",
            category="BACKUP_ARCHIVE",
            state=State.BLOCKED,
            user_ids=frozenset(["user_c07"]),
        )
    ]
    view_blocked = View(audit_at="2026-09-03T00:00:00Z", facts=facts_blocked)
    owned_blocked = OwnedResource(
        system_id="backup_service",
        resource_id="backup_archive_02",
        category="BACKUP_ARCHIVE",
        signal="identifier",
    )
    state_b = recon.reconstruct(owned_blocked, view_blocked, case)
    steps_b = compiler.compile_resource(state_b, is_case_complete=True)
    assert len(steps_b) == 1
    assert steps_b[0].operation == "VERIFY_RESTORE_BLOCKED"
    assert steps_b[0].state == "BLOCKED"
    assert steps_b[0].evidence_id == "ev_backup_blocked"


# ---------------------------------------------------------------------------
# Case 8: Tombstone Dirty (PII Exposed) vs Clean
# ---------------------------------------------------------------------------
def test_case_custom_08_tombstone_dirty_vs_clean():
    """A dirty tombstone with exposed direct identifiers must trigger REDACT_RECORD remediation."""
    case = Case(
        case_id="case_c08",
        email="c08@example.com",
        requested_at="2026-09-01T00:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-09-02T00:00:00Z",
        audit_at="2026-09-03T00:00:00Z",
        request_text="Delete my account",
    )
    facts_dirty = [
        Fact(
            file_id="ev_dirty",
            captured_at="2026-09-02T12:00:00Z",
            system_id="account_service",
            resource_id="acc_dirty",
            category="ACCOUNT_TOMBSTONE",
            state=State.PRESENT,  # PII still present
            user_ids=frozenset(["user_c08"]),
            emails=frozenset(["c08@example.com"]),
        )
    ]
    view_dirty = View(audit_at="2026-09-03T00:00:00Z", facts=facts_dirty)
    owned_dirty = OwnedResource(
        system_id="account_service",
        resource_id="acc_dirty",
        category="ACCOUNT_TOMBSTONE",
        signal="identifier",
    )
    recon = StateReconstructor()
    res_state = recon.reconstruct(owned_dirty, view_dirty, case)
    compiler = PolicyCompiler()
    steps_d = compiler.compile_resource(res_state, is_case_complete=False)
    ops_d = [s.operation for s in steps_d]
    assert "REPORT_EXPOSED_PII" in ops_d
    assert "REDACT_RECORD" in ops_d
    assert "VERIFY_RECORD_REDACTED" in ops_d
