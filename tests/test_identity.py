"""Unit tests for identity resolution and anti-leakage search surface (ghost/identity.py)."""
from __future__ import annotations
import hashlib
import pytest
from ghost.identity import build_bag, resolve_user_id, _sha256, load_identities, load_audit_log
from ghost.types import Case, IdentityBag
from ghost.config import USER_IDENTITIES_PATH, USER_AUDIT_LOG_PATH


@pytest.fixture(scope="module")
def dataset_identities():
    return load_identities(USER_IDENTITIES_PATH)


@pytest.fixture(scope="module")
def dataset_audit_log():
    return load_audit_log(USER_AUDIT_LOG_PATH)


def test_current_email_case_insensitive(dataset_identities, dataset_audit_log):
    """Resolve current user with mixed case."""
    # user_01 is Amina El-Masri, amina.elmasri@gmail.com
    uid = resolve_user_id("AMINA.ELMASRI@GMAIL.COM", dataset_identities, dataset_audit_log)
    assert uid == "user_01"


def test_historical_only_email_resolution(dataset_identities, dataset_audit_log):
    """Resolve user using an old email found only in user_audit_log.csv."""
    # Find a user with an email change in audit log
    email_events = [e for e in dataset_audit_log if e["field_name"] == "email" and e["old_value"]]
    assert len(email_events) > 0
    event = email_events[0]
    old_email = event["old_value"]
    expected_uid = event["user_id"]

    resolved_uid = resolve_user_id(old_email.upper(), dataset_identities, dataset_audit_log)
    assert resolved_uid == expected_uid


def test_rollback_future_audit_events():
    """Verify state at audit_at rolls back future changes (event_time > audit_at)."""
    identities = {
        "user_999": {
            "user_id": "user_999",
            "name": "Jane Doe",
            "email": "jane.new@example.com",
            "phone": "+1 555 9999",
            "email_hash": _sha256("jane.new@example.com"),
            "updated_at": "2026-09-20T12:00:00Z",
        }
    }
    audit_log = [
        {
            "audit_id": "aud_1",
            "user_id": "user_999",
            "event_time": "2026-09-15T10:00:00Z",  # After audit_at
            "field_name": "email",
            "old_value": "jane.old@example.com",
            "new_value": "jane.new@example.com",
        },
        {
            "audit_id": "aud_2",
            "user_id": "user_999",
            "event_time": "2026-09-16T10:00:00Z",  # Also after audit_at
            "field_name": "phone",
            "old_value": "+1 555 1111",
            "new_value": "+1 555 9999",
        },
    ]

    case = Case(
        case_id="test_case_rollback",
        email="jane.old@example.com",
        requested_at="2026-09-10T10:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-09-11T10:00:00Z",
        audit_at="2026-09-12T12:00:00Z",  # Cutoff before 09-15 and 09-16
        request_text="Delete my data",
    )

    bag = build_bag(case, identities, audit_log)

    # Active values at audit_at must be the rolled-back values
    assert bag.active_at_audit["email"] == "jane.old@example.com"
    assert bag.active_at_audit["phone"] == "+1 555 1111"
    assert bag.active_at_audit["email_hash"] == _sha256("jane.old@example.com")


def test_anti_leakage_post_cutoff_exclusion():
    """Verify that identifiers introduced strictly AFTER audit_at never enter search_surface."""
    identities = {
        "user_999": {
            "user_id": "user_999",
            "name": "Jane Doe",
            "email": "jane.future@example.com",
            "phone": "+1 555 9999",
            "email_hash": _sha256("jane.future@example.com"),
            "updated_at": "2026-10-01T12:00:00Z",
        }
    }
    audit_log = [
        {
            "audit_id": "aud_future",
            "user_id": "user_999",
            "event_time": "2026-09-25T10:00:00Z",  # Post cutoff
            "field_name": "email",
            "old_value": "jane.past@example.com",
            "new_value": "jane.future@example.com",
        }
    ]

    case = Case(
        case_id="test_anti_leakage",
        email="jane.past@example.com",
        requested_at="2026-09-10T10:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-09-11T10:00:00Z",
        audit_at="2026-09-12T12:00:00Z",  # Cutoff before 09-25
        request_text="Delete my account",
    )

    bag = build_bag(case, identities, audit_log)

    # Past email must be in search surface
    assert "jane.past@example.com" in bag.search_surface
    assert _sha256("jane.past@example.com") in bag.search_surface

    # Future email and its hash MUST NOT be in search surface
    assert "jane.future@example.com" not in bag.search_surface
    assert _sha256("jane.future@example.com") not in bag.search_surface


def test_sha256_hashing():
    """Verify email hashes match lowercase sha256."""
    raw = "Test.User+Filter@Domain.COM"
    expected = hashlib.sha256("test.user+filter@domain.com".encode("utf-8")).hexdigest()
    assert _sha256(raw) == expected
