"""Test refined pipeline on 32 samples with improved ownership and state."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path('code')))

import csv, json
from datetime import datetime, timedelta
from ghost.identity import load_identities, load_audit_log, build_bag
from ghost.ledger import Ledger, View
from ghost.types import OwnedResource, ResourceState, State, normalize_system_id, infer_category, VALID_SYSTEMS
from ghost.policy import PolicyCompiler, sort_steps
from evaluation.score import score_predictions

def parse_iso(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

repo_root = Path('.')
dataset_dir = repo_root / 'dataset'

identities = load_identities(dataset_dir / 'user_identities.csv')
audit_log = load_audit_log(dataset_dir / 'user_audit_log.csv')
ledger = Ledger()
ledger.ingest_manifest(dataset_dir / 'evidence_files.csv', dataset_dir)
compiler = PolicyCompiler()

with open(dataset_dir / 'sample_deletion_requests.csv', 'r', encoding='utf-8') as f:
    sample_requests = list(csv.DictReader(f))

with open(dataset_dir / 'sample_output.csv', 'r', encoding='utf-8') as f:
    sample_truth = list(csv.DictReader(f))

with open(dataset_dir / 'system_activity.csv', 'r', encoding='utf-8') as f:
    activities = list(csv.DictReader(f))

# Map file -> other user accounts mentioned
known_other_accounts = set()
handover_file = dataset_dir / 'evidence/records/customer_account_handover_20261001.txt'
if handover_file.exists():
    import re
    # matches like account_XXXX
    pass

pred_rows = []
unresolved_cases = []

for req in sample_requests:
    case_id = req['case_id']
    audit_at = req['audit_at']
    requested_at = req['requested_at']
    reported_at = req['reported_at']
    reported_status = req['reported_status']
    bag = build_bag(req, identities, audit_log)
    view = ledger.admissible(audit_at)

    candidates = {}

    # 1. Evidence matches via search_surface
    for ident in bag.search_surface:
        if not ident: continue
        for fact in view.by_identifier(ident):
            norm_sys = normalize_system_id(fact.resource_id, fact.system_id)
            if norm_sys not in VALID_SYSTEMS:
                continue
            cat = fact.category or infer_category(fact.resource_id, norm_sys)
            key = (norm_sys, fact.resource_id)
            if key not in candidates:
                candidates[key] = OwnedResource(
                    system_id=norm_sys,
                    resource_id=fact.resource_id,
                    category=cat,
                    signal="identifier",
                )

    # 2. Activity catalog links within request lifetime
    for act in activities:
        if act.get('event_type') == 'LINK_RESOURCE_IDENTITY':
            event_time = act.get('event_time', '')
            if not (requested_at <= event_time <= audit_at):
                continue
            details = act.get('details', '')
            if any(len(ident) > 3 and ident.lower() in details.lower() for ident in bag.search_surface):
                res_id = act.get('resource_id', '').strip(' \t\n\r"\'\\')
                raw_sys = act.get('target_system', '')
                norm_sys = normalize_system_id(res_id, raw_sys)
                if norm_sys not in VALID_SYSTEMS:
                    continue
                cat = infer_category(res_id, norm_sys)
                key = (norm_sys, res_id)
                if key not in candidates:
                    candidates[key] = OwnedResource(
                        system_id=norm_sys,
                        resource_id=res_id,
                        category=cat,
                        signal="relational",
                    )

    # 3. Account corroboration when no account is grounded
    has_account = any(r.system_id == "account_service" for r in candidates.values())
    if not has_account and reported_at:
        try:
            rep_dt = parse_iso(reported_at)
            req_dt = parse_iso(requested_at) if requested_at else rep_dt - timedelta(hours=2)
            w_start = min(req_dt, rep_dt - timedelta(hours=2))
            w_end = rep_dt + timedelta(minutes=15)

            acc_acts = []
            for act in activities:
                if act.get('source_system') == 'deletion_worker' and act.get('target_system') == 'account_service':
                    et = act.get('event_time', '')
                    if et <= audit_at:
                        act_dt = parse_iso(et)
                        if w_start <= act_dt <= w_end:
                            acc_acts.append(act)

            if len(acc_acts) == 1:
                res_id = acc_acts[0].get('resource_id', '').strip(' \t\n\r"\'\\')
                if res_id:
                    candidates[("account_service", res_id)] = OwnedResource(
                        system_id="account_service",
                        resource_id=res_id,
                        category="USER_PROFILE",
                        signal="activity_corroboration",
                    )
            elif len(acc_acts) > 1:
                # Disambiguate by reported status and timing
                # If case has tombstone, correlate with tombstone event timing
                tombstone = [r for r in candidates.values() if r.category == "ACCOUNT_TOMBSTONE"]
                matched_act = None
                if tombstone:
                    t_res = tombstone[0].resource_id
                    # find activity for tombstone
                    t_acts = [a for a in activities if a.get('resource_id') == t_res]
                    if t_acts:
                        t_time = parse_iso(t_acts[0]['event_time'])
                        # find closest account act preceding tombstone
                        prec = [a for a in acc_acts if parse_iso(a['event_time']) <= t_time]
                        if prec:
                            matched_act = prec[-1]

                if not matched_act:
                    # Filter by status: SUCCESS vs PARTIAL
                    target_res = "SUCCESS" if reported_status == "COMPLETE" else "PARTIAL"
                    status_matches = [a for a in acc_acts if a.get('reported_result') == target_res]
                    if len(status_matches) == 1:
                        matched_act = status_matches[0]

                if matched_act:
                    res_id = matched_act.get('resource_id', '').strip(' \t\n\r"\'\\')
                    candidates[("account_service", res_id)] = OwnedResource(
                        system_id="account_service",
                        resource_id=res_id,
                        category="USER_PROFILE",
                        signal="activity_corroboration",
                    )
        except Exception as e:
            pass

    # Sort candidates
    owned_resources = sorted(candidates.values(), key=lambda r: (r.system_id, r.resource_id))

    # State reconstruction
    states = []
    for owned in owned_resources:
        facts = view.all_for_resource(owned.system_id, owned.resource_id)
        if facts:
            facts.sort(key=lambda x: x.captured_at)
            latest_time = facts[-1].captured_at
            latest_facts = [f for f in facts if f.captured_at == latest_time]
            selected_fact = latest_facts[-1]
            for f in latest_facts:
                if f.state in {State.PRESENT, State.ACTIVE}:
                    selected_fact = f
                    break

            st = selected_fact.state
            if owned.system_id == "integration_service":
                if st not in {State.ACTIVE, State.DISABLED}:
                    st = State.ACTIVE if st == State.PRESENT else State.DISABLED
                cat = "DATA_FLOW"
            elif owned.system_id == "backup_service":
                if st not in {State.ACTIVE, State.BLOCKED}:
                    st = State.ACTIVE if st == State.PRESENT else State.BLOCKED
                cat = "BACKUP_ARCHIVE"
            elif owned.category == "SECURITY_AUDIT_LOG":
                st = State.PRESENT
                cat = "SECURITY_AUDIT_LOG"
            elif owned.category in {"SUPPORT_MESSAGE", "ACCOUNT_TOMBSTONE"}:
                st = State.REDACTED if (not selected_fact.emails and not selected_fact.phones and not selected_fact.hashes) else State.PRESENT
                cat = owned.category

            states.append(ResourceState(
                system_id=owned.system_id,
                resource_id=owned.resource_id,
                category=cat,
                state=st,
                evidence_id=selected_fact.file_id,
                is_unresolved=False,
            ))
        else:
            # Absence via covering snapshot
            covering_file_id = view.covering_snapshot(owned.system_id)
            if covering_file_id:
                st = State.ANONYMIZED if owned.category == "ANALYTICS_PROFILE" else State.ABSENT
                states.append(ResourceState(
                    system_id=owned.system_id,
                    resource_id=owned.resource_id,
                    category=owned.category,
                    state=st,
                    evidence_id=covering_file_id,
                    is_unresolved=False,
                ))
            else:
                # Patch P3 fallback: never invent absence
                unresolved_cases.append((case_id, owned.system_id, owned.resource_id))
                fallback_state = State.ACTIVE if owned.category in {"DATA_FLOW", "BACKUP_ARCHIVE"} else State.PRESENT
                states.append(ResourceState(
                    system_id=owned.system_id,
                    resource_id=owned.resource_id,
                    category=owned.category,
                    state=fallback_state,
                    evidence_id="",
                    is_unresolved=True,
                ))

    has_finding = False
    for st in states:
        cat = st.category
        if cat in {'USER_PROFILE', 'SEARCH_INDEX_ENTRY', 'SUPPORT_ATTACHMENT', 'USER_EXPORT', 'MARKETING_PROFILE', 'SECONDARY_IDENTIFIER', 'CACHE_ENTRY'}:
            if st.state.value == "PRESENT":
                has_finding = True
        elif cat in {'SUPPORT_MESSAGE', 'ACCOUNT_TOMBSTONE', 'EMAIL_DELIVERY_LOG'}:
            if st.state.value == "PRESENT":
                has_finding = True
        elif cat in {'ANALYTICS_PROFILE', 'PRODUCT_TELEMETRY'}:
            if st.state.value == "PRESENT":
                has_finding = True
        elif cat == 'BACKUP_ARCHIVE':
            if st.state.value == "ACTIVE":
                has_finding = True
        elif cat == 'DATA_FLOW':
            if st.state.value == "ACTIVE":
                has_finding = True

    pred_status = "INCOMPLETE" if has_finding else "COMPLETE"
    is_complete = (pred_status == "COMPLETE")
    raw_steps = []
    for st in states:
        raw_steps.extend(compiler.compile_resource(st, is_case_complete=is_complete))

    final_steps = sort_steps(raw_steps)
    pred_rows.append({
        "case_id": case_id,
        "deletion_status": pred_status,
        "steps_json": json.dumps(final_steps, separators=(',', ':')),
    })

print(f"Unresolved fallback count on samples: {len(unresolved_cases)}: {unresolved_cases}")
for p, t in zip(pred_rows, sample_truth):
    if p['deletion_status'] != t['deletion_status']:
        print(f"Status Mismatch: {p['case_id']} Pred={p['deletion_status']} Truth={t['deletion_status']}")
metrics = score_predictions(pred_rows, sample_truth, verbose=True)
