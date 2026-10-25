"""Scorer for Ghost Data Still Exists deletion-audit predictions.

Computes:
- Case-level deletion status accuracy
- Row exact match rate
- Step-level precision, recall, and F1 (on 5-tuple: phase, system_id, resource_id, operation, state)
- Field-level accuracy (phase, system_id, resource_id, operation, state, evidence_id)
- Sequence exact match and Longest Common Subsequence (LCS) ratio: 2 * LCS / (|P| + |G|)
- Error taxonomy categorization (intent, state, ownership/identity, policy, evidence_id, ordering)
"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path
from typing import Any


def _lcs_length(seq1: list[dict], seq2: list[dict]) -> int:
    """Calculate length of longest common subsequence between two step sequences."""
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            s1, s2 = seq1[i], seq2[j]
            # Match on core step identity: phase, system_id, resource_id, operation, state, evidence_id
            match = (
                s1.get("phase") == s2.get("phase")
                and s1.get("system_id") == s2.get("system_id")
                and s1.get("resource_id") == s2.get("resource_id")
                and s1.get("operation") == s2.get("operation")
                and s1.get("state") == s2.get("state")
                and s1.get("evidence_id") == s2.get("evidence_id")
            )
            if match:
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i + 1][j], dp[i][j + 1])
    return dp[m][n]


def _step_key(s: dict) -> tuple[str, str, str, str, str]:
    return (
        s.get("phase", ""),
        s.get("system_id", ""),
        s.get("resource_id", ""),
        s.get("operation", ""),
        s.get("state", ""),
    )


def score_predictions(
    predicted_rows: list[dict[str, Any]],
    truth_rows: list[dict[str, Any]],
    verbose: bool = True,
) -> dict[str, Any]:
    """Score predicted rows against ground truth rows."""
    truth_by_id = {r["case_id"]: r for r in truth_rows}
    pred_by_id = {r["case_id"]: r for r in predicted_rows}

    all_case_ids = list(truth_by_id.keys())
    total_cases = len(all_case_ids)
    if total_cases == 0:
        raise ValueError("No ground truth cases provided for scoring.")

    status_correct = 0
    row_exact_match = 0
    seq_exact_match = 0

    total_pred_steps = 0
    total_truth_steps = 0
    total_step_intersections = 0

    lcs_ratios: list[float] = []

    field_totals = {
        "phase": 0,
        "system_id": 0,
        "resource_id": 0,
        "operation": 0,
        "state": 0,
        "evidence_id": 0,
    }
    field_matches = {k: 0 for k in field_totals}

    taxonomy = {
        "intent_errors": 0,
        "state_errors": 0,
        "ownership_identity_errors": 0,
        "policy_errors": 0,
        "evidence_id_errors": 0,
        "ordering_errors": 0,
    }

    for case_id in all_case_ids:
        t_row = truth_by_id[case_id]
        p_row = pred_by_id.get(case_id)

        if not p_row:
            taxonomy["intent_errors"] += 1
            lcs_ratios.append(0.0)
            continue

        t_status = t_row["deletion_status"]
        p_status = p_row["deletion_status"]

        try:
            t_steps = json.loads(t_row.get("steps_json", "[]"))
        except Exception:
            t_steps = []

        try:
            p_steps = json.loads(p_row.get("steps_json", "[]"))
        except Exception:
            p_steps = []

        # 1. Status accuracy
        status_match = t_status == p_status
        if status_match:
            status_correct += 1
        else:
            if t_status == "NOT_APPLICABLE" or p_status == "NOT_APPLICABLE":
                taxonomy["intent_errors"] += 1
            else:
                taxonomy["state_errors"] += 1

        # 2. Row exact match
        # Check normalized JSON representation equality
        steps_exact = (len(t_steps) == len(p_steps)) and all(
            t_s == p_s for t_s, p_s in zip(t_steps, p_steps)
        )
        if status_match and steps_exact:
            row_exact_match += 1

        # 3. Step 5-tuple precision/recall
        t_step_keys = set(_step_key(s) for s in t_steps)
        p_step_keys = set(_step_key(s) for s in p_steps)

        intersection = t_step_keys & p_step_keys
        total_pred_steps += len(p_step_keys)
        total_truth_steps += len(t_step_keys)
        total_step_intersections += len(intersection)

        # Check for ownership or policy discrepancies
        t_resources = {(s.get("system_id"), s.get("resource_id")) for s in t_steps}
        p_resources = {(s.get("system_id"), s.get("resource_id")) for s in p_steps}
        if t_resources != p_resources:
            taxonomy["ownership_identity_errors"] += 1
        elif t_step_keys != p_step_keys:
            taxonomy["policy_errors"] += 1

        # 4. Sequence exact match & LCS ratio
        if steps_exact:
            seq_exact_match += 1

        if len(p_steps) == 0 and len(t_steps) == 0:
            lcs_ratios.append(1.0)
        else:
            denom = len(p_steps) + len(t_steps)
            lcs = _lcs_length(p_steps, t_steps)
            lcs_ratio = (2.0 * lcs) / denom
            lcs_ratios.append(lcs_ratio)
            if t_step_keys == p_step_keys and not steps_exact:
                taxonomy["ordering_errors"] += 1

        # 5. Field-level accuracy
        # Align by index up to max length, or match on 5-tuple
        # To evaluate field accuracy rigorously:
        # Match each predicted step to the best ground truth step with the same (system_id, resource_id)
        # If identical, aligned 1:1
        matched_truth_indices = set()
        for p_step in p_steps:
            best_match = None
            best_idx = None
            # First try exact 5-tuple
            for idx, t_step in enumerate(t_steps):
                if idx in matched_truth_indices:
                    continue
                if _step_key(p_step) == _step_key(t_step):
                    best_match = t_step
                    best_idx = idx
                    break
            # Second try same system and resource
            if best_match is None:
                for idx, t_step in enumerate(t_steps):
                    if idx in matched_truth_indices:
                        continue
                    if (
                        p_step.get("system_id") == t_step.get("system_id")
                        and p_step.get("resource_id") == t_step.get("resource_id")
                    ):
                        best_match = t_step
                        best_idx = idx
                        break

            if best_match is not None:
                matched_truth_indices.add(best_idx)
                for field_name in field_totals:
                    field_totals[field_name] += 1
                    if p_step.get(field_name) == best_match.get(field_name):
                        field_matches[field_name] += 1
                    elif field_name == "evidence_id":
                        taxonomy["evidence_id_errors"] += 1
            else:
                for field_name in field_totals:
                    field_totals[field_name] += 1

        # Any unaligned ground truth step counts against field totals
        unmatched_truth = len(t_steps) - len(matched_truth_indices)
        for _ in range(unmatched_truth):
            for field_name in field_totals:
                field_totals[field_name] += 1

    case_accuracy = status_correct / total_cases
    row_accuracy = row_exact_match / total_cases
    seq_accuracy = seq_exact_match / total_cases
    mean_lcs = sum(lcs_ratios) / len(lcs_ratios) if lcs_ratios else 0.0

    step_precision = (
        (total_step_intersections / total_pred_steps) if total_pred_steps > 0 else 1.0
    )
    step_recall = (
        (total_step_intersections / total_truth_steps) if total_truth_steps > 0 else 1.0
    )
    if step_precision + step_recall > 0:
        step_f1 = (2.0 * step_precision * step_recall) / (step_precision + step_recall)
    else:
        step_f1 = 0.0

    field_accuracy = {}
    for f, total in field_totals.items():
        field_accuracy[f] = (field_matches[f] / total) if total > 0 else 1.0

    results = {
        "total_cases": total_cases,
        "case_status_accuracy": case_accuracy,
        "row_exact_match_rate": row_accuracy,
        "step_precision": step_precision,
        "step_recall": step_recall,
        "step_f1": step_f1,
        "sequence_exact_match_rate": seq_accuracy,
        "mean_lcs_ratio": mean_lcs,
        "field_accuracy": field_accuracy,
        "error_taxonomy": taxonomy,
    }

    if verbose:
        print("=" * 60)
        print("EVALUATION SCORER REPORT")
        print("=" * 60)
        print(f"Total Cases:                 {total_cases}")
        print(f"Case Status Accuracy:        {case_accuracy * 100:.2f}% ({status_correct}/{total_cases})")
        print(f"Row Exact Match Rate:        {row_accuracy * 100:.2f}% ({row_exact_match}/{total_cases})")
        print(f"Step Precision:              {step_precision * 100:.2f}%")
        print(f"Step Recall:                 {step_recall * 100:.2f}%")
        print(f"Step F1 Score:               {step_f1 * 100:.2f}%")
        print(f"Sequence Exact Match:        {seq_accuracy * 100:.2f}% ({seq_exact_match}/{total_cases})")
        print(f"Sequence Mean LCS Ratio:     {mean_lcs * 100:.2f}%")
        print("-" * 60)
        print("Field-Level Accuracy:")
        for f, acc in field_accuracy.items():
            print(f"  - {f:<15}            {acc * 100:.2f}% ({field_matches[f]}/{field_totals[f]})")
        print("-" * 60)
        print("Error Taxonomy Counts:")
        for err_type, count in taxonomy.items():
            print(f"  - {err_type:<25}  {count}")
        print("=" * 60)

    return results


def score_files(predicted_csv: str | Path, ground_truth_csv: str | Path, verbose: bool = True) -> dict[str, Any]:
    """Score predicted CSV file against ground truth CSV file."""
    with open(ground_truth_csv, "r", encoding="utf-8") as f:
        truth_rows = list(csv.DictReader(f))
    with open(predicted_csv, "r", encoding="utf-8") as f:
        pred_rows = list(csv.DictReader(f))
    return score_predictions(pred_rows, truth_rows, verbose=verbose)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        # Default to sample_output against itself if no arguments given
        default_path = Path(__file__).resolve().parent.parent.parent / "dataset" / "sample_output.csv"
        if default_path.exists():
            score_files(default_path, default_path)
            sys.exit(0)
        print("Usage: python score.py <predicted_csv> <ground_truth_csv>")
        sys.exit(1)

    score_files(sys.argv[1], sys.argv[2])
