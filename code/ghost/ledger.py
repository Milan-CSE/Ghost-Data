"""Evidence ledger and point-in-time admissible view (ledger.py)."""
from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any
from ghost.types import Fact, State
from ghost.adapters import parse_evidence_file


class View:
    """Immutable point-in-time view of admissible facts as of audit_at."""

    def __init__(self, audit_at: str, facts: list[Fact]):
        self.audit_at = audit_at
        # Later containers are admissible only when each record carries its own
        # explicit timestamp and that record is at or before the audit cutoff.
        self.facts = [
            f for f in facts
            if f.captured_at <= audit_at and (
                f.has_independent_timestamp
                or not f.file_captured_at
                or f.file_captured_at <= audit_at
            )
        ]

        self._by_resource: dict[tuple[str, str], list[Fact]] = defaultdict(list)
        self._by_identifier: dict[str, list[Fact]] = defaultdict(list)
        self._covering_by_system: dict[str, list[Fact]] = defaultdict(list)

        for f in self.facts:
            key = (f.system_id, f.resource_id)
            self._by_resource[key].append(f)

            if f.covers_system:
                self._covering_by_system[f.system_id].append(f)

            for ident in f.user_ids | f.emails | f.hashes | f.phones:
                self._by_identifier[ident.strip().lower()].append(f)

        # Sort indexed lists by captured_at ascending
        for key in self._by_resource:
            self._by_resource[key].sort(key=lambda x: x.captured_at)

        for key in self._covering_by_system:
            self._covering_by_system[key].sort(key=lambda x: x.captured_at)

        for key in self._by_identifier:
            self._by_identifier[key].sort(key=lambda x: x.captured_at)

    def latest(self, system_id: str, resource_id: str) -> Fact | None:
        """Return the latest admissible Fact for (system_id, resource_id).
        
        If multiple observations have the exact same latest timestamp, prioritizes
        PRESENT / ACTIVE (detecting surviving copies or replication drift).
        """
        facts = self._by_resource.get((system_id, resource_id), [])
        if not facts:
            return None

        latest_time = facts[-1].captured_at
        latest_candidates = [f for f in facts if f.captured_at == latest_time]
        if len(latest_candidates) == 1:
            return latest_candidates[0]

        # Prioritize observations that prove surviving data (e.g. failover replica drift)
        for cand in latest_candidates:
            if cand.state in {State.PRESENT, State.ACTIVE}:
                return cand

        return latest_candidates[-1]

    def all_for_resource(self, system_id: str, resource_id: str) -> list[Fact]:
        """Return all admissible facts for (system_id, resource_id)."""
        return list(self._by_resource.get((system_id, resource_id), []))

    def covering_snapshot(self, system_id: str) -> str | None:
        """Return file_id of the latest covering observation across all formats.
        
        Cross-format covering index spans SQL dumps, JSON snapshot bundles, and ledgers,
        ensuring newer snapshot bundles correctly supersede older SQL dumps (e.g. case_31).
        """
        covering_facts = self._covering_by_system.get(system_id, [])
        if not covering_facts:
            return None

        # Return the file_id of the latest covering snapshot
        latest_covering = covering_facts[-1]
        return latest_covering.file_id

    def latest_covering_fact(self, system_id: str) -> Fact | None:
        """Return the latest covering Fact object for a system across all formats."""
        covering_facts = self._covering_by_system.get(system_id, [])
        return covering_facts[-1] if covering_facts else None

    def by_identifier(self, identifier: str) -> list[Fact]:
        """Lookup all admissible facts associated with an identifier."""
        return list(self._by_identifier.get(identifier.strip().lower(), []))

    def citation_for(self, fact: Fact) -> str:
        """Prefer a same-state citation whose evidence container predates the cutoff."""
        if not fact.file_captured_at or fact.file_captured_at <= self.audit_at:
            return fact.file_id
        def citation_state(candidate: Fact):
            if candidate.category in {"BACKUP_ARCHIVE", "DATA_FLOW", "INTEGRATION_DATA_FLOW"}:
                if candidate.state in {State.PRESENT, State.ACTIVE}:
                    return State.ACTIVE
                if candidate.state in {State.ABSENT, State.DISABLED, State.BLOCKED}:
                    return candidate.state
            return candidate.state

        prior = [
            candidate for candidate in self._by_resource.get((fact.system_id, fact.resource_id), [])
            if citation_state(candidate) == citation_state(fact)
            and candidate.file_captured_at
            and candidate.file_captured_at <= self.audit_at
        ]
        if prior:
            return max(prior, key=lambda candidate: candidate.captured_at).file_id
        return fact.file_id


class Ledger:
    """Central store for normalized observations across all evidence sources."""

    def __init__(self):
        self._facts: list[Fact] = []

    def add(self, facts: list[Fact] | Fact) -> None:
        """Add one or more facts to the ledger."""
        if isinstance(facts, list):
            self._facts.extend(facts)
        else:
            self._facts.append(facts)

    def count(self) -> int:
        return len(self._facts)

    def admissible(self, audit_at: str) -> View:
        """Construct an immutable point-in-time View containing only facts captured_at <= audit_at."""
        return View(audit_at=audit_at, facts=self._facts)

    def ingest_manifest(
        self,
        manifest_csv: Path | str,
        dataset_root: Path | str | None = None,
    ) -> int:
        """Parse all evidence files in evidence_files.csv into the ledger."""
        manifest_path = Path(manifest_csv)
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        base_dir = Path(dataset_root) if dataset_root else manifest_path.parent
        new_facts_count = 0

        with open(manifest_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                file_id = row["file_id"]
                file_rel = row["file_path"]
                captured_at = row["captured_at"]

                file_path = base_dir / file_rel
                if file_path.exists():
                    facts = parse_evidence_file(file_path, file_id=file_id, captured_at=captured_at)
                    for f in facts:
                        if not f.file_captured_at:
                            f_with_fc = Fact(
                                file_id=f.file_id,
                                captured_at=f.captured_at,
                                system_id=f.system_id,
                                resource_id=f.resource_id,
                                category=f.category,
                                state=f.state,
                                emails=f.emails,
                                hashes=f.hashes,
                                user_ids=f.user_ids,
                                phones=f.phones,
                                store=f.store,
                                covers_system=f.covers_system,
                                file_captured_at=captured_at,
                                has_independent_timestamp=f.has_independent_timestamp,
                            )
                            self._facts.append(f_with_fc)
                        else:
                            self._facts.append(f)
                    new_facts_count += len(facts)

        return new_facts_count
