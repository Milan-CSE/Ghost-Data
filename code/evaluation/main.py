"""Evaluation entry point for Ghost Data Still Exists."""
from __future__ import annotations
import sys
from pathlib import Path

# Support running as a script directly
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from evaluation.score import score_files
else:
    from .score import score_files


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    sample_output = repo_root / "dataset" / "sample_output.csv"
    if len(sys.argv) >= 3:
        pred_csv = Path(sys.argv[1])
        truth_csv = Path(sys.argv[2])
    elif len(sys.argv) == 2:
        pred_csv = Path(sys.argv[1])
        truth_csv = sample_output
    else:
        output_csv = repo_root / "output.csv"
        if output_csv.exists() and output_csv.stat().st_size > 50:
            pred_csv = output_csv
            truth_csv = sample_output
        else:
            pred_csv = sample_output
            truth_csv = sample_output

    score_files(pred_csv, truth_csv)


if __name__ == "__main__":
    main()
