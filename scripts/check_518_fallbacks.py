import sys
from pathlib import Path
sys.path.insert(0, "code")

import csv
from ghost.pipeline import AuditContext
from ghost.intent import classify
from ghost.identity import build_bag

ctx = AuditContext.load("dataset")

with open("dataset/deletion_requests.csv", "r", encoding="utf-8") as f:
    cases = list(csv.DictReader(f))

fallbacks = []

for c in cases:
    cid = c["case_id"]
    intent = classify(c, ctx.linker._activities, use_llm=False)
    if intent.is_not_deletion:
        continue
    bag = build_bag(c, ctx.identities, ctx.audit_log)
    view = ctx.ledger.admissible(c["audit_at"])
    owned = ctx.linker.link(c, bag, view)
    states = [ctx.state_recon.reconstruct(o, view, c) for o in owned]
    for st in states:
        if st.is_unresolved:
            fallbacks.append((cid, st.system_id, st.resource_id, st.state.value, st.evidence_id))

print(f"Total distinct fallback occurrences across 518 cases: {len(fallbacks)}")
for cid, sys_id, res_id, st_val, ev_id in fallbacks:
    print(f"  - {cid}: {sys_id}/{res_id} (state={st_val}, ev={ev_id})")
