"""Run evaluation pipeline across all 518 requests in dataset/deletion_requests.csv."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path("code")))

import csv
import json
from collections import Counter
from ghost.identity import load_identities, load_audit_log, build_bag
from ghost.ledger import Ledger
from ghost.ownership import OwnershipLinker
from ghost.state import StateReconstructor
from ghost.policy import PolicyCompiler, sort_steps

def main():
    repo_root = Path(".")
    dataset_dir = repo_root / "dataset"

    identities = load_identities(dataset_dir / "user_identities.csv")
    audit_log = load_audit_log(dataset_dir / "user_audit_log.csv")
    ledger = Ledger()
    ledger.ingest_manifest(dataset_dir / "evidence_files.csv", dataset_dir)
    linker = OwnershipLinker(dataset_dir / "system_activity.csv")
    state_recon = StateReconstructor()
    compiler = PolicyCompiler()

    with open(dataset_dir / "deletion_requests.csv", "r", encoding="utf-8") as f:
        requests = list(csv.DictReader(f))

    print(f"Total requests loaded: {len(requests)}")

    no_account_cases = []
    multi_account_cases = []
    total_fallbacks = 0
    status_counts = Counter()
    output_rows = []

    for req in requests:
        case_id = req["case_id"]
        bag = build_bag(req, identities, audit_log)
        view = ledger.admissible(req["audit_at"])
        owned_resources = linker.link(req, bag, view)

        account_resources = [r for r in owned_resources if r.system_id == "account_service"]
        if len(account_resources) == 0:
            no_account_cases.append(case_id)
        elif len(account_resources) > 1:
            multi_account_cases.append((case_id, [r.resource_id for r in account_resources]))

        states = [state_recon.reconstruct(owned, view, req) for owned in owned_resources]
        for st in states:
            if st.is_unresolved:
                total_fallbacks += 1

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
        # Note: intent classification for NOT_APPLICABLE is deferred to Step 5 per plan
        status_counts[pred_status] += 1

        is_complete = (pred_status == "COMPLETE")
        raw_steps = []
        for st in states:
            raw_steps.extend(compiler.compile_resource(st, is_case_complete=is_complete))

        final_steps = sort_steps(raw_steps)
        output_rows.append({
            "case_id": case_id,
            "deletion_status": pred_status,
            "steps_json": json.dumps(final_steps, separators=(",", ":")),
        })

    print(f"Cases with no account resource linked: {len(no_account_cases)} ({no_account_cases[:10]}...)")
    print(f"Cases with more than one candidate account: {len(multi_account_cases)} ({multi_account_cases[:10]}...)")
    print(f"Total fallback count across all 518 cases: {total_fallbacks}")
    print(f"Status distribution: {dict(status_counts)}")

if __name__ == "__main__":
    main()
