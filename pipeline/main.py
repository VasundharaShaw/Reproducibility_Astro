"""
pipeline/main.py — Reproducibility Astro pipeline entry point.

Usage:
    python3 pipeline/main.py collect          # fetch articles from NASA ADS
    python3 pipeline/main.py mentions         # extract notebook mentions from arXiv
    python3 pipeline/main.py run              # clone repos, score, execute notebooks
    python3 pipeline/main.py run --count N    # process N repos (default: 10)
    python3 pipeline/main.py score --repo-dir <path> --repo-id <int>

Environment variables required:
    ADS_API_TOKEN   — NASA ADS API token
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Ensure project root is on sys.path so config and pipeline packages resolve
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.config import DB_FILE, ADS_API_TOKEN, require_ads_token


# ── Subcommand handlers ────────────────────────────────────────────────────────

def cmd_collect(args) -> int:
    """Fetch articles from NASA ADS and populate the database."""
    try:
        require_ads_token()
    except EnvironmentError as e:
        print(e, file=sys.stderr)
        return 1
    print("[MAIN] Running collect_ads.py ...")
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "pipeline" / "collect_ads.py")],
        env={**__import__("os").environ},
    )
    return result.returncode


def cmd_mentions(args) -> int:
    """Extract notebook mentions from arXiv LaTeX sources."""
    print("[MAIN] Running extract_mentions.py ...")
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "pipeline" / "extract_mentions.py")],
        env={**__import__("os").environ},
    )
    return result.returncode


def cmd_run(args) -> int:
    """Clone repos, score with RRS, execute notebooks."""
    import os
    env = {**os.environ, "TARGET_COUNT": str(args.count)}
    print(f"[MAIN] Running pipeline (TARGET_COUNT={args.count}) ...")
    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "pipeline" / "main.sh")],
        env=env,
    )
    return result.returncode


def cmd_score(args) -> int:
    """Score a single cloned repository with RRS."""
    if not args.repo_dir or not args.repo_id:
        print("[ERROR] --repo-dir and --repo-id are required for score.", file=sys.stderr)
        return 1
    print(f"[MAIN] Scoring repo_id={args.repo_id} at {args.repo_dir} ...")
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "pipeline" / "score.py"),
            "--repo-dir", args.repo_dir,
            "--repo-id", str(args.repo_id),
            "--db", str(DB_FILE),
        ],
        env={**__import__("os").environ},
    )
    return result.returncode


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Reproducibility Astro — pipeline entry point",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("collect",  help="Fetch articles from NASA ADS")
    sub.add_parser("mentions", help="Extract notebook mentions from arXiv")

    run_p = sub.add_parser("run", help="Clone, score, and execute repos")
    run_p.add_argument("--count", type=int, default=10,
                       help="Number of repos to process (default: 10)")

    score_p = sub.add_parser("score", help="Score a single cloned repo")
    score_p.add_argument("--repo-dir", required=True, help="Path to cloned repo")
    score_p.add_argument("--repo-id", required=True, type=int,
                         help="Row ID in repo_targets table")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "collect":  cmd_collect,
        "mentions": cmd_mentions,
        "run":      cmd_run,
        "score":    cmd_score,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
