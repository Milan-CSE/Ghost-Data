"""Tests for intent classification module (code/ghost/intent.py).

Covers:
- Affirmative deletion vs informational / hypothetical inquiries
- Target-scoped negation, discourse reversal, contrast clauses, and auxiliary requests
- Telemetry cutoff and account-matching boundaries
- Conservative fallback
- Exact classification of the 10 dataset non-deletion requests
"""
from __future__ import annotations
import pytest
from ghost.types import Case, Intent
from ghost.intent import classify


def test_intent_affirmative_deletion_mandates():
    """Verify primary affirmative deletion authorizations across multiple phrasings."""
    samples = [
        "Please permanently delete the account associated with this email address.",
        "I want to close this account and have its associated personal data deleted.",
        "Please erase the account linked to this email address.",
        "Solicito a exclusão permanente da conta associada a este e-mail.",
        "Je demande la suppression définitive du compte associé à cette adresse e-mail.",
        "Please process a permanent account-deletion request for this email address.",
    ]
    for text in samples:
        case = Case(
            case_id="test_case",
            email="test@example.com",
            requested_at="2026-09-01T12:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T12:00:00Z",
            audit_at="2026-09-03T12:00:00Z",
            request_text=text,
        )
        res = classify(case, use_llm=False)
        assert res.is_deletion is True, f"Failed on affirmative: {text}"
        assert res.tier == 4


def test_intent_informational_and_hypothetical_inquiries():
    """Informational or hypothetical inquiries without operative deletion commands are NOT_APPLICABLE."""
    samples = [
        "Can you tell me what personal information you hold about me? This is an information request, not a request to erase it.",
        "What happens if I delete my account? How does the deletion process work?",
        "Could you send me a copy of the information held on my account? I still use it, so please don't delete or change anything.",
        "I need a copy of last year's invoices for my records. Please leave my profile and purchase history in place.",
    ]
    for text in samples:
        case = Case(
            case_id="test_case",
            email="test@example.com",
            requested_at="2026-09-01T12:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T12:00:00Z",
            audit_at="2026-09-03T12:00:00Z",
            request_text=text,
        )
        res = classify(case, use_llm=False)
        assert res.is_not_deletion is True, f"Failed on informational: {text}"
        assert res.tier in (2, 3)


def test_intent_target_scoped_negation_and_retention():
    """Target-scoped negation of account deletion produces NOT_APPLICABLE."""
    samples = [
        "Please stop the promotional emails. I still need the account and my order history, so I am not asking for deletion.",
        "I can't access my profile and need help resetting the login. Do not close the account.",
        "Please remove me from marketing lists only. I still want receipts and service messages for this account.",
        "The mobile number on my profile is out of date. Please replace it with the new one and leave the account active.",
    ]
    for text in samples:
        case = Case(
            case_id="test_case",
            email="test@example.com",
            requested_at="2026-09-01T12:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-09-02T12:00:00Z",
            audit_at="2026-09-03T12:00:00Z",
            request_text=text,
        )
        res = classify(case, use_llm=False)
        assert res.is_not_deletion is True, f"Failed on negation: {text}"
        assert res.tier in (2, 3)


def test_intent_discourse_reversal():
    """Discourse reversal markers mean the latest clause governs."""
    text = "Please delete my account immediately. Wait, stop, cancel that, do not close the account."
    case = Case(
        case_id="test_rev",
        email="test@example.com",
        requested_at="2026-09-01T12:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-09-02T12:00:00Z",
        audit_at="2026-09-03T12:00:00Z",
        request_text=text,
    )
    res = classify(case, use_llm=False)
    assert res.is_not_deletion is True
    assert res.tier == 3


def test_intent_correlative_and_auxiliary_clauses():
    """Correlative addition ('not only ... but also') and auxiliary requests do not negate deletion mandate."""
    text = (
        "Not only do I want you to erase my account, but also please confirm when done. "
        "You may retain tax invoices as required by statutory law."
    )
    case = Case(
        case_id="test_aux",
        email="test@example.com",
        requested_at="2026-09-01T12:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-09-02T12:00:00Z",
        audit_at="2026-09-03T12:00:00Z",
        request_text=text,
    )
    res = classify(case, use_llm=False)
    assert res.is_deletion is True
    assert res.tier == 4


def test_intent_telemetry_corroboration_and_boundaries():
    """Telemetry matching requires account identity and requested_at <= event_time <= min(reported_at, audit_at)."""
    ambiguous_text = "I have a question regarding my profile records."
    case = Case(
        case_id="test_telem",
        email="test@example.com",
        requested_at="2026-09-01T10:00:00Z",
        reported_status="COMPLETE",
        reported_at="2026-09-02T10:00:00Z",
        audit_at="2026-09-03T10:00:00Z",
        request_text=ambiguous_text,
    )

    # 1. Matching event within boundary
    act_match = [
        {
            "activity_id": "act_match",
            "event_time": "2026-09-01T11:00:00Z",
            "event_type": "CLASSIFY_REQUEST",
            "resource_id": "account_100",
            "details": "Classified as non-deletion; marketing opt-out.",
        }
    ]
    res1 = classify(case, activity=act_match, resolved_account_id="account_100", use_llm=False)
    assert res1.is_not_deletion is True
    assert res1.tier == 5

    # 2. Event for a different account must NOT match
    res2 = classify(case, activity=act_match, resolved_account_id="account_999", use_llm=False)
    assert res2.tier == 6  # Falls through to conservative fallback

    # 3. Post-cutoff event (> min(reported_at, audit_at)) must NOT match
    act_late = [
        {
            "activity_id": "act_late",
            "event_time": "2026-09-02T11:00:00Z",  # after reported_at
            "event_type": "CLASSIFY_REQUEST",
            "resource_id": "account_100",
            "details": "Classified as non-deletion.",
        }
    ]
    res3 = classify(case, activity=act_late, resolved_account_id="account_100", use_llm=False)
    assert res3.tier == 6


def test_intent_dataset_10_non_deletion_cases():
    """All 10 non-deletion requests in dataset/deletion_requests.csv are correctly classified."""
    import csv
    with open("dataset/deletion_requests.csv", "r", encoding="utf-8") as f:
        cases = {r["case_id"]: r for r in csv.DictReader(f)}

    non_del_ids = [f"case_{i}" for i in range(533, 543)]
    for cid in non_del_ids:
        c = cases[cid]
        res = classify(c, use_llm=False)
        assert res.is_not_deletion is True, f"{cid} was expected to be NOT_APPLICABLE, got {res.decision}"
        assert res.tier in (2, 3), f"{cid} had unexpected tier {res.tier}"
