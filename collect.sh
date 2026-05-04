#!/bin/bash
###############################################################################
# collect.sh — Data Collection Entry Point
#
# Fetches astrophysics articles from NASA ADS that mention Jupyter notebooks
# (across any hosting platform), classifies each article by notebook category,
# and populates data/db.sqlite with journal, article, author, repositories,
# and notebook_mentions (schema only) tables.
#
# Usage:
#   export ADS_API_TOKEN=your_token_here
#   bash collect.sh
#
# Run this before mentions.sh and run.sh.
###############################################################################
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "   Reproducibility Astro — Data Collection"
echo "============================================"
echo ""

# ── Dependency checks ──────────────────────────────────────────────────────────
fail() { echo "[ERROR] $*"; exit 1; }

command -v python3 >/dev/null 2>&1 || fail "python3 not found."
command -v sqlite3 >/dev/null 2>&1 || fail "sqlite3 not found."

# ── ADS token check ────────────────────────────────────────────────────────────
if [ -z "$ADS_API_TOKEN" ]; then
    echo "[ERROR] ADS_API_TOKEN is not set."
    echo ""
    echo "  Get a free token at: https://ui.adsabs.harvard.edu"
    echo "  → sign in → Account → Settings → API Token"
    echo ""
    echo "  Then run:"
    echo "    export ADS_API_TOKEN=your_token_here"
    echo "    bash collect.sh"
    exit 1
fi

echo "[CHECK] ADS_API_TOKEN is set."
echo "[CHECK] python3 found."
echo ""

# ── Fetch and populate in one step ────────────────────────────────────────────
echo "--------------------------------------------"
echo " Fetching from NASA ADS → data/db.sqlite"
echo "--------------------------------------------"

python3 "$SCRIPT_DIR/pipeline/collect_ads.py"

echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "============================================"
echo " Data collection complete."
echo " data/db.sqlite — populated with articles,"
echo "   journals, authors, repositories, and"
echo "   notebook_mentions table (schema ready)."
echo ""
echo " Next steps:"
echo "   bash mentions.sh   # extract arXiv mention context"
echo "   bash run.sh        # clone and execute notebooks"
echo "============================================"
