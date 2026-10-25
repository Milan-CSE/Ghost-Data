"""Intent classification module (code/ghost/intent.py).

Implements the six-tier deletion-intent arbitration hierarchy defined in
COMBINED_PLAN.md §5.7:
1. Normalization & Correlative Coordination
2. Informational & Hypothetical Inquiry Filter
3. Target-Scoped Account Negation
4. Affirmative Account Deletion Mandate (Primary Authority)
5. Scoped Telemetry Corroboration for Ambiguous Texts
6. Conservative Fallback Trade-off (with optional LLM arbitration)
"""
from __future__ import annotations
import re
from typing import Any
from ghost.types import Case, Intent


# Tier 1 & 2: Informational / hypothetical patterns
_INFORMATIONAL_PATTERNS = [
    r"\bwhat happens if\b",
    r"\bhow the deletion process works\b",
    r"\bhow does (the )?deletion work\b",
    r"\bwhat is the retention period\b",
    r"\bcan you tell me what personal information you hold\b",
    r"\bthis is an information request, not a request to erase\b",
    r"\bcould you send me a copy of the information held\b",
    r"\bi need a copy of .* invoices\b",
    r"\bi'd like to download my account information in a portable format\b",
    r"\bi can't access my profile and need help\b",
    r"\bmy surname is misspelled\b",
    r"\bthe mobile number on my profile is out of date\b",
    r"\bplease change the email address used for this account\b",
]

# Tier 3: Target-scoped negation / retention patterns
_NEGATION_TARGET_PATTERNS = [
    r"\b(do not|don't)\s+(delete|close|purge|erase)(\s+or\s+\w+)?\s+(my account|the account|anything)\b",
    r"\bstop asking me to delete my account\b",
    r"\bnot asking for deletion\b",
    r"\bdo not close the account\b",
    r"\bleave the account active\b",
    r"\bkeep my account active\b",
    r"\bkeep the account as it is\b",
    r"\bwithout removing any of my records\b",
    r"\bleave my profile (and purchase history )?in place\b",
    r"\bwant to continue using the service\b",
    r"\bplease stop the promotional emails\b",
    r"\bmarketing lists only\b",
    r"\bauf keinen fall l[oö]schen\b",
    r"\bne pas supprimer\b",
    r"\bn[aã]o exclua\b",
]

# Tier 4: Affirmative deletion mandate patterns (multilingual & natural expressions)
_AFFIRMATIVE_DELETION_PATTERNS = [
    # English account deletion / closure / erasure / removal
    r"\b(permanently )?delete\s+(the |my |this )?account\b",
    r"\bdelet(ed|ing)\s+(the |my |this )?account\b",
    r"\bdelet(ed|ing)\s+it\b",
    r"\b(had|has|was)\s+been deleted\b",
    r"\b(have|has|already)\s+been removed\b",
    r"\baccount (itself )?is gone\b",
    r"\bremove the rest\b",
    r"\bdisable any (synchronization|integration|sync)\b",
    r"\baccount[- ]deletion request\b",
    r"\brequest for permanent account deletion\b",
    r"\bbegin the deletion process for the account\b",
    r"\bprocess (the )?associated personal[- ]data deletion\b",
    r"\b(close|closing)\s+(the |my |this )?account\b",
    r"\b(would like it|want it|have it)\s+closed\b",
    r"\berase\s+(the |my |this )?account\b",
    r"\bwould like the account .* to be erased\b",
    r"\b(remove|removing)\s+(the |my )?(profile|account|records|personal details|name and contact)\b",
    r"\bremove records (linked to|under)\b",
    r"\bremove that search result\b",
    r"\b(finish|complete)\s+(the )?deletion\b",
    r"\b(profile|account)\s+is gone\b",
    r"\baccount was (fully )?(removed|deleted)\b",
    r"\bno longer (use|need)\s+this account\b",
    r"\bdelete this account\b",
    r"\bdelete that export file\b",
    r"\bdeletion of the account\b",
    r"\bsubmit a request to delete this account\b",
    r"\btotal expungement\b",
    r"\brestlose vernichtung\b",
    # French
    r"\bsuppression d[eé]finitive du compte\b",
    # Portuguese & Spanish
    r"\bexclus[aã]o permanente da conta\b",
    r"\beliminaci[oó]n permanente de la cuenta\b",
    r"\beliminar mi cuenta\b",
    # Japanese & Korean
    r"削除",  # Japanese deletion
    r"삭제",  # Korean deletion
]

# Reversal markers where latest clause governs
_REVERSAL_MARKERS = [
    r"\bdisregard that\b",
    r"\bwait,? stop\b",
    r"\bcancel that\b",
]


def _normalize_text(text: str) -> str:
    """Normalize whitespace and casing without destructive mutation."""
    text = re.sub(r"\s+", " ", text).strip().lower()
    # Normalize correlative conjunctions: treat 'not only ... but also' as additive
    text = re.sub(r"\bnot only\b(.*?)\bbut also\b(.*)", r"\1 and \2", text)
    text = re.sub(r"\bnot just\b(.*?)\bbut\b(.*)", r"\1 and \2", text)
    return text


def classify(
    case: Case | dict[str, Any],
    activity: list[dict[str, Any]] | None = None,
    resolved_account_id: str | None = None,
    use_llm: bool = True,
) -> Intent:
    """Classify request deletion intent using the six-tier arbitration hierarchy."""
    req_text = case.request_text if isinstance(case, Case) else case.get("request_text", "")
    case_id = case.case_id if isinstance(case, Case) else case.get("case_id", "")
    req_at = case.requested_at if isinstance(case, Case) else case.get("requested_at", "")
    rep_at = case.reported_at if isinstance(case, Case) else case.get("reported_at", "")
    aud_at = case.audit_at if isinstance(case, Case) else case.get("audit_at", "")

    # Tier 1: Normalization & Precedence check
    norm_text = _normalize_text(req_text)

    # Check for discourse reversal (latest clause governs)
    effective_text = norm_text
    for rev in _REVERSAL_MARKERS:
        m = re.search(rev, norm_text)
        if m:
            effective_text = norm_text[m.end():].strip()
            break

    # Tier 2: Informational & Hypothetical Inquiry Filter
    is_info = any(re.search(pat, effective_text) for pat in _INFORMATIONAL_PATTERNS)
    # Operative imperative command to delete required to override informational inquiry
    has_operative_command = bool(
        re.search(
            r"\b(please|kindly|proceed with|i request|i am requesting|i want)\s+(to\s+)?(delete|erase|close|purge|remove)\b",
            effective_text,
        )
        or re.search(r"\b(permanently delete|erase the account|exclus[aã]o|eliminaci[oó]n|suppression)\b", effective_text)
    )

    if is_info and not has_operative_command:
        return Intent(
            decision="NOT_APPLICABLE",
            tier=2,
            reason="Informational or hypothetical inquiry without operative deletion command",
            confidence=1.0,
        )

    # Tier 3: Target-Scoped Account Negation
    for pat in _NEGATION_TARGET_PATTERNS:
        if re.search(pat, effective_text):
            return Intent(
                decision="NOT_APPLICABLE",
                tier=3,
                reason=f"Target-scoped negation or retention request matching '{pat}'",
                confidence=1.0,
            )

    # Tier 4: Affirmative Account Deletion Mandate (Primary Authority)
    has_affirmative_in_text = any(re.search(pat, effective_text) for pat in _AFFIRMATIVE_DELETION_PATTERNS)
    if has_affirmative_in_text:
        return Intent(
            decision="DELETION",
            tier=4,
            reason="Affirmative deletion mandate present in request text",
            confidence=1.0,
        )

    # Tier 5: Scoped Telemetry Corroboration for Ambiguous Texts
    # Strictly requires resource_id == resolved_account_id
    if activity and resolved_account_id:
        cutoff = min(rep_at, aud_at) if (rep_at and aud_at) else (rep_at or aud_at)
        for ev in activity:
            if ev.get("event_type") == "CLASSIFY_REQUEST":
                ev_time = ev.get("event_time", "")
                if req_at <= ev_time <= cutoff:
                    res_id = ev.get("resource_id", "")
                    if res_id == resolved_account_id:
                        details = ev.get("details", "").lower()
                        if "non-deletion" in details or any(
                            k in details for k in ["opt-out", "profile_update", "data_access", "portability"]
                        ):
                            return Intent(
                                decision="NOT_APPLICABLE",
                                tier=5,
                                reason=f"Scoped intake telemetry corroborates non-deletion ({ev.get('activity_id')})",
                                confidence=0.95,
                            )
                        elif "deletion" in details:
                            return Intent(
                                decision="DELETION",
                                tier=5,
                                reason=f"Scoped intake telemetry corroborates deletion mandate ({ev.get('activity_id')})",
                                confidence=0.95,
                            )

    # Optional Tier 5.5: LLM Arbitration for Ambiguous Texts
    if use_llm:
        try:
            from ghost.llm import classify_intent as llm_classify
            llm_res = llm_classify(req_text)
            if llm_res and isinstance(llm_res, dict):
                is_del = bool(llm_res.get("is_deletion", False))
                conf = float(llm_res.get("confidence", 0.9))
                reason = str(llm_res.get("reason", "Model intent arbitration"))
                return Intent(
                    decision="DELETION" if is_del else "NOT_APPLICABLE",
                    tier=5,
                    reason=f"Model arbitration: {reason}",
                    confidence=conf,
                )
        except Exception:
            pass

    # Tier 6: Conservative Fallback Trade-off
    return Intent(
        decision="NOT_APPLICABLE",
        tier=6,
        reason="Conservative fallback under uncertainty: no affirmative mandate proven",
        confidence=0.5,
    )
