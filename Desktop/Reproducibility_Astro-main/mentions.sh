#!/bin/bash
###############################################################################
# mentions.sh — Notebook Mention Extraction Entry Point
#
# For each article in data/db.sqlite that has an arXiv ID, fetches the
# LaTeX source tarball from arXiv and extracts every notebook mention into
# the notebook_mentions table.
#
# Must be run after collect.sh.
#
# Usage:
#   bash mentions.sh
#
# No API token required. arXiv requests are rate-limited to 1 per 3 seconds
# as per arXiv bulk-access guidelines.
###############################################################################
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "   Reproducibility Astro — Mention Extraction"
echo "============================================"
echo ""

# ── Dependency checks ──────────────────────────────────────────────────────────
fail() { echo "[ERROR] $*"; exit 1; }

command -v python3 >/dev/null 2>&1 || fail "python3 not found."
command -v sqlite3 >/dev/null 2>&1 || fail "sqlite3 not found."

# ── Database check ─────────────────────────────────────────────────────────────
DB_FILE="$SCRIPT_DIR/data/db.sqlite"

if [ ! -f "$DB_FILE" ]; then
    echo "[ERROR] data/db.sqlite not found."
    echo ""
    echo "  Run collect.sh first to populate the database:"
    echo "    bash collect.sh"
    exit 1
fi

ARTICLE_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM article;" 2>/dev/null || echo "0")
if [ "$ARTICLE_COUNT" -eq 0 ]; then
    echo "[ERROR] No articles found in data/db.sqlite."
    echo ""
    echo "  Run collect.sh first:"
    echo "    bash collect.sh"
    exit 1
fi

echo "[CHECK] python3 found."
echo "[CHECK] sqlite3 found."
echo "[CHECK] data/db.sqlite found — $ARTICLE_COUNT articles."
echo ""

# ── Run extraction ─────────────────────────────────────────────────────────────
echo "--------------------------------------------"
echo " Fetching arXiv source → notebook_mentions"
echo "--------------------------------------------"
echo ""
echo " Note: arXiv requests are rate-limited to 1 per 3 seconds."
echo " Large collections will take time — do not interrupt."
echo ""

python3 "$SCRIPT_DIR/pipeline/extract_mentions.py" "$@"

echo ""

# ── Summary query ──────────────────────────────────────────────────────────────
MENTION_COUNT=$(sqlite3 "$DB_FILE" \
    "SELECT COUNT(*) FROM notebook_mentions WHERE mention_text NOT LIKE '__%__';" \
    2>/dev/null || echo "0")

echo "============================================"
echo " Mention extraction complete."
echo ""
echo " notebook_mentions rows : $MENTION_COUNT"
echo ""
echo " Category breakdown:"
sqlite3 "$DB_FILE" \
    "SELECT notebook_category, COUNT(*) FROM article GROUP BY notebook_category ORDER BY COUNT(*) DESC;" \
    2>/dev/null | awk -F'|' '{printf "   %-35s %s\n", $1, $2}'
echo ""
echo " You can now run the pipeline:"
echo "   bash run.sh"
echo "============================================"
