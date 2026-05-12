#!/usr/bin/env python3
"""
pipeline/score.py — ReproScore: five-category reproducibility scoring.

Usage:
    python3 pipeline/score.py --repo-dir <path> --repo-id <int> --db <path>

Scores a cloned repository across five categories (0–5 each, 25 total)
and writes results back to the repositories table in the output DB.

Categories:
    score_env   — environment specification
    score_data  — data accessibility
    score_docs  — documentation
    score_code  — code quality
    score_repro — reproducibility signals
    score_total — sum of above
"""

import argparse
import json
import os
import re
import sqlite3
import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_files(root, filename):
    """Return list of paths matching filename (case-insensitive) under root."""
    matches = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower() == filename.lower():
                matches.append(os.path.join(dirpath, f))
    return matches


def find_files_pattern(root, pattern):
    """Return list of paths whose filename matches a regex pattern."""
    matches = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if re.search(pattern, f, re.IGNORECASE):
                matches.append(os.path.join(dirpath, f))
    return matches


def read_text(path, max_bytes=50_000):
    """Read a text file safely, returning empty string on failure."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read(max_bytes)
    except OSError:
        return ""


def dir_exists(root, dirname):
    """Return True if a directory named dirname exists anywhere under root."""
    for dirpath, dirnames, _ in os.walk(root):
        if dirname.lower() in [d.lower() for d in dirnames]:
            return True
    return False


def count_notebooks(root):
    """Return list of .ipynb paths under root (excluding checkpoints)."""
    nbs = []
    for dirpath, _, filenames in os.walk(root):
        if ".ipynb_checkpoints" in dirpath:
            continue
        for f in filenames:
            if f.endswith(".ipynb"):
                nbs.append(os.path.join(dirpath, f))
    return nbs


def load_notebook(path):
    """Parse a notebook JSON, return dict or None on failure."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def get_readme_text(root):
    """Return text of the top-level README (any extension)."""
    for name in os.listdir(root):
        if name.lower().startswith("readme"):
            path = os.path.join(root, name)
            if os.path.isfile(path):
                return read_text(path)
    return ""


# ---------------------------------------------------------------------------
# Category scorers (each returns int 0–5)
# ---------------------------------------------------------------------------

def score_environment(root):
    """
    Environment specification (0–5).

    Points:
        +1  requirements.txt present
        +2  environment.yml present
        +2  Dockerfile present
        +1  setup.py or setup.cfg or pyproject.toml present
    Capped at 5.
    """
    points = 0

    if find_files(root, "requirements.txt"):
        points += 1
    if find_files(root, "environment.yml") or find_files(root, "environment.yaml"):
        points += 2
    if find_files(root, "Dockerfile"):
        points += 2
    if (find_files(root, "setup.py")
            or find_files(root, "setup.cfg")
            or find_files(root, "pyproject.toml")):
        points += 1

    return min(points, 5)


def score_data(root):
    """
    Data accessibility (0–5).

    Points:
        +2  README or any notebook mentions a Zenodo or DOI link
        +1  a /data or /dataset(s) directory exists
        +1  a download script exists (download*.py / fetch*.py / get_data*.py)
        +1  a data-specific README or LICENSE exists inside a data folder
    Capped at 5.
    """
    points = 0

    # Zenodo / DOI references in README or notebooks
    readme = get_readme_text(root)
    zenodo_doi_re = re.compile(r"zenodo\.org|10\.\d{4,}/", re.IGNORECASE)
    if zenodo_doi_re.search(readme):
        points += 2
    else:
        # Check notebooks for DOI/Zenodo mentions
        for nb_path in count_notebooks(root):
            nb = load_notebook(nb_path)
            if not nb:
                continue
            for cell in nb.get("cells", []):
                src = "".join(cell.get("source", []))
                if zenodo_doi_re.search(src):
                    points += 2
                    break
            if points >= 2:
                break

    # Data directory
    if dir_exists(root, "data") or dir_exists(root, "dataset") or dir_exists(root, "datasets"):
        points += 1

    # Download script
    dl_pattern = r"^(download|fetch|get_data).*\.py$"
    if find_files_pattern(root, dl_pattern):
        points += 1

    # Data-level README/LICENSE
    data_dirs = []
    for dirpath, dirnames, _ in os.walk(root):
        for d in dirnames:
            if d.lower() in ("data", "dataset", "datasets"):
                data_dirs.append(os.path.join(dirpath, d))
    for d in data_dirs:
        for name in os.listdir(d):
            if name.lower().startswith("readme") or name.lower().startswith("license"):
                points += 1
                break

    return min(points, 5)


def score_docs(root):
    """
    Documentation (0–5).

    Points:
        +1  README present
        +1  README > 500 chars
        +1  README > 2000 chars
        +1  at least one notebook has markdown cells
        +1  average markdown cells per notebook >= 3
    Capped at 5.
    """
    points = 0

    readme = get_readme_text(root)
    if readme:
        points += 1
        if len(readme) > 500:
            points += 1
        if len(readme) > 2000:
            points += 1

    nb_paths = count_notebooks(root)
    if nb_paths:
        md_counts = []
        for nb_path in nb_paths:
            nb = load_notebook(nb_path)
            if not nb:
                continue
            md = sum(1 for c in nb.get("cells", []) if c.get("cell_type") == "markdown")
            md_counts.append(md)
        if md_counts:
            if any(c > 0 for c in md_counts):
                points += 1
            if (sum(md_counts) / len(md_counts)) >= 3:
                points += 1

    return min(points, 5)


def score_code(root):
    """
    Code quality (0–5).

    Points:
        +1  no notebooks with >20% empty code cells
        +1  at least one notebook defines a function (def keyword)
        +1  no notebooks with bare broad except clauses (except:)
        +1  no notebooks whose last code cell ends in a raw error output
        +1  notebooks organised in subdirectories or repo has a src/ layout
    Capped at 5.
    """
    points = 0

    nb_paths = count_notebooks(root)

    if not nb_paths:
        # Can't judge code quality without notebooks
        return 0

    empty_cell_violations = 0
    has_function = False
    bare_except_violations = 0
    error_output_violations = 0

    for nb_path in nb_paths:
        nb = load_notebook(nb_path)
        if not nb:
            continue

        cells = nb.get("cells", [])
        code_cells = [c for c in cells if c.get("cell_type") == "code"]
        if not code_cells:
            continue

        # Empty cell ratio
        empty = sum(1 for c in code_cells if not "".join(c.get("source", [])).strip())
        if len(code_cells) > 0 and (empty / len(code_cells)) > 0.20:
            empty_cell_violations += 1

        for cell in code_cells:
            src = "".join(cell.get("source", []))
            if re.search(r"\bdef\s+\w+", src):
                has_function = True
            if re.search(r"^\s*except\s*:", src, re.MULTILINE):
                bare_except_violations += 1

        # Last code cell error output
        last = code_cells[-1]
        for output in last.get("outputs", []):
            if output.get("output_type") == "error":
                error_output_violations += 1

    if empty_cell_violations == 0:
        points += 1
    if has_function:
        points += 1
    if bare_except_violations == 0:
        points += 1
    if error_output_violations == 0:
        points += 1

    # Organised layout: notebooks in subdirs or src/ exists
    nb_in_subdirs = any(
        os.path.dirname(p) != root for p in nb_paths
    )
    if nb_in_subdirs or dir_exists(root, "src"):
        points += 1

    return min(points, 5)


def score_repro(root):
    """
    Reproducibility signals (0–5).

    Points:
        +2  .github/workflows/ directory exists (CI configured)
        +1  any notebook sets a random seed (numpy/random/torch)
        +1  tests/ or test/ directory exists, or pytest.ini / tox.ini present
        +1  README contains a Zenodo badge or Binder badge
    Capped at 5.
    """
    points = 0

    # CI
    ci_dir = os.path.join(root, ".github", "workflows")
    if os.path.isdir(ci_dir) and os.listdir(ci_dir):
        points += 2

    # Random seed
    seed_re = re.compile(
        r"(np\.random\.seed|random\.seed|torch\.manual_seed|tf\.random\.set_seed"
        r"|jax\.random\.PRNGKey)",
        re.IGNORECASE,
    )
    for nb_path in count_notebooks(root):
        nb = load_notebook(nb_path)
        if not nb:
            continue
        for cell in nb.get("cells", []):
            if cell.get("cell_type") == "code":
                src = "".join(cell.get("source", []))
                if seed_re.search(src):
                    points += 1
                    break
        else:
            continue
        break

    # Tests
    if (dir_exists(root, "tests")
            or dir_exists(root, "test")
            or find_files(root, "pytest.ini")
            or find_files(root, "tox.ini")):
        points += 1

    # Zenodo / Binder badge in README
    readme = get_readme_text(root)
    badge_re = re.compile(r"zenodo\.org/badge|mybinder\.org/badge", re.IGNORECASE)
    if badge_re.search(readme):
        points += 1

    return min(points, 5)


# ---------------------------------------------------------------------------
# DB write
# ---------------------------------------------------------------------------

def write_scores(db_path, repo_id, scores):
    """Write score columns to repositories table."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Add columns if missing (safe for existing DBs)
    for col in ("score_env", "score_data", "score_docs", "score_code", "score_repro", "score_total"):
        try:
            cur.execute(f"ALTER TABLE repositories ADD COLUMN {col} INTEGER")
        except sqlite3.OperationalError:
            pass  # column already exists

    cur.execute(
        """UPDATE repositories
           SET score_env=?, score_data=?, score_docs=?, score_code=?, score_repro=?, score_total=?
           WHERE id=?""",
        (
            scores["score_env"],
            scores["score_data"],
            scores["score_docs"],
            scores["score_code"],
            scores["score_repro"],
            scores["score_total"],
            repo_id,
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ReproScore: score a cloned repo.")
    parser.add_argument("--repo-dir", required=True, help="Path to cloned repo root")
    parser.add_argument("--repo-id", required=True, type=int, help="Row ID in repositories table")
    parser.add_argument("--db", required=True, help="Path to output SQLite DB")
    args = parser.parse_args()

    if not os.path.isdir(args.repo_dir):
        print(f"[SCORE] ERROR: repo dir not found: {args.repo_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[SCORE] Scoring repo_id={args.repo_id} at {args.repo_dir}")

    env   = score_environment(args.repo_dir)
    data  = score_data(args.repo_dir)
    docs  = score_docs(args.repo_dir)
    code  = score_code(args.repo_dir)
    repro = score_repro(args.repo_dir)
    total = env + data + docs + code + repro

    scores = {
        "score_env":   env,
        "score_data":  data,
        "score_docs":  docs,
        "score_code":  code,
        "score_repro": repro,
        "score_total": total,
    }

    print(f"[SCORE] env={env} data={data} docs={docs} code={code} repro={repro} total={total}/25")

    write_scores(args.db, args.repo_id, scores)
    print(f"[SCORE] Written to DB (repo_id={args.repo_id})")


if __name__ == "__main__":
    main()
