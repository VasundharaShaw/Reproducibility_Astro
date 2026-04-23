#!/bin/bash
###############################################################################
# collect.sh — Data Collection Entry Point
#
# Fetches high-energy astrophysics articles from NASA ADS that mention
# GitHub and Jupyter notebooks, then populates data/db.sqlite with
# journal, article, author, and repositories tables.
#
# Usage:
#   export ADS_API_TOKEN=your_token_here
#   bash collect.sh
#
# Run this before run.sh — it populates the repositories table that
# the pipeline reads in batch mode.
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

# ── Step 1: Fetch articles from NASA ADS ──────────────────────────────────────

echo "--------------------------------------------"
echo " Step 1: Fetching articles from NASA ADS"
echo "--------------------------------------------"
python3 "$SCRIPT_DIR/pipeline/r0_ads_article_db.py"
echo ""

# ── Step 2: Parse and populate the database ───────────────────────────────────

echo "--------------------------------------------"
echo " Step 2: Populating database"
echo "--------------------------------------------"
python3 "$SCRIPT_DIR/pipeline/r1_ads_article_metadata.py"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────

echo "============================================"
echo " Data collection complete."
echo " data/ads_results.json  — raw ADS results"
echo " data/db.sqlite         — populated database"
echo ""
echo " You can now run the pipeline:"
echo "   bash run.sh"
echo "============================================"
