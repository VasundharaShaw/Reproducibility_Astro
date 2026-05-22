"""
pipeline/score.py — Reproducibility Readiness Score (RRS) scoring.

Usage:
    python3 pipeline/score.py --repo-dir <path> --repo-id <int> --db <path>

Scores a cloned repository using the 26-sub-metric RRS framework (ReproScore)
and writes results to the repo_targets table in the single output DB.

Columns written (all REAL, 0–100):
    rrs      — overall Reproducibility Readiness Score
    score_E  — Environment specification
    score_A  — Data accessibility
    score_D  — Documentation
    score_C  — Code portability
    score_S  — Reproducibility signals
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Ensure pipeline/ is on sys.path so the vendored reproscore package is importable
sys.path.insert(0, str(Path(__file__).parent))

from reproscore.scoring.rrs import RRSScorer


# ---------------------------------------------------------------------------
# DB write
# ---------------------------------------------------------------------------

def write_scores(db_path: str, repo_id: int, result) -> None:
    """Write RRS category and overall scores to repo_targets table."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """UPDATE repo_targets
           SET rrs=?, score_E=?, score_A=?, score_D=?, score_C=?, score_S=?
           WHERE id=?""",
        (
            result.rrs,
            result.category_scores["E"].raw_score,
            result.category_scores["A"].raw_score,
            result.category_scores["D"].raw_score,
            result.category_scores["C"].raw_score,
            result.category_scores["S"].raw_score,
            repo_id,
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="RRS: score a cloned repository.")
    parser.add_argument("--repo-dir", required=True, help="Path to cloned repo root")
    parser.add_argument("--repo-id", required=True, type=int,
                        help="Row ID in repo_targets table")
    parser.add_argument("--db", required=True, help="Path to SQLite DB")
    args = parser.parse_args()

    if not Path(args.repo_dir).is_dir():
        print(f"[SCORE] ERROR: repo dir not found: {args.repo_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[SCORE] Scoring repo_id={args.repo_id} at {args.repo_dir}")

    scorer = RRSScorer()
    result = scorer.score(args.repo_dir)

    cats = result.category_scores
    print(
        f"[SCORE] RRS={result.rrs:.1f}  "
        f"E={cats['E'].raw_score:.0f}  A={cats['A'].raw_score:.0f}  "
        f"D={cats['D'].raw_score:.0f}  C={cats['C'].raw_score:.0f}  "
        f"S={cats['S'].raw_score:.0f}"
    )
    if result.penalty_environment or result.penalty_data or result.penalty_seed:
        print(
            f"[SCORE] Penalties applied: "
            f"env={result.penalty_environment}  "
            f"data={result.penalty_data}  "
            f"seed={result.penalty_seed}"
        )

    write_scores(args.db, args.repo_id, result)
    print(f"[SCORE] Written to DB (repo_id={args.repo_id})")


if __name__ == "__main__":
    main()
