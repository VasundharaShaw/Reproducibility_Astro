#!/bin/bash
###############################################################################
# quickstart.sh — Run the full pipeline end-to-end (limited to 5 repos)
#
# Usage:
#   export ADS_API_TOKEN=your_token_here
#   bash quickstart.sh
###############################################################################

set -e

# ── Check tokens ─────────────────────────────────────────────────────────────
if [ -z "$ADS_API_TOKEN" ]; then
    echo ""
    echo "  ERROR: ADS_API_TOKEN is not set."
    echo ""
    echo "  Get a free token at: https://ui.adsabs.harvard.edu"
    echo "    → sign in → Account → Settings → API Token"
    echo ""
    echo "  Then run:"
    echo "    export ADS_API_TOKEN=your_token_here"
    echo "    bash quickstart.sh"
    echo ""
    exit 1
fi

echo "========================================="
echo "  Reproducibility Astro — Quick Start"
echo "========================================="
echo ""

# ── Step 1: Collect papers from NASA ADS ─────────────────────────────────────
echo "[1/4] Collecting papers from NASA ADS..."
bash collect.sh

# ── Step 2: Extract notebook mentions from arXiv (limit 5) ──────────────────
echo ""
echo "[2/4] Extracting notebook mentions from arXiv (limit 5)..."
bash mentions.sh --limit 5

# ── Step 3: Run the pipeline on 5 repos (batch mode) ────────────────────────
echo ""
echo "[3/4] Running pipeline on 5 repositories..."
export TARGET_COUNT=5
echo "2" | bash run.sh

# ── Step 4: Show results ─────────────────────────────────────────────────────
echo ""
echo "[4/4] Results:"
echo ""
python3 -c "
import sqlite3

conn = sqlite3.connect('output/db/db.sqlite')

print('=== ReproScores ===')
print(f'{\"Repository\":<45} {\"env\":>3} {\"data\":>4} {\"docs\":>4} {\"code\":>4} {\"repro\":>5} {\"TOTAL\":>5}')
print('-' * 72)

rows = conn.execute('''
    SELECT repository, score_env, score_data, score_docs, score_code, score_repro, score_total
    FROM repositories
    ORDER BY score_total DESC
''').fetchall()

for r in rows:
    name = r[0][:44]
    scores = ['—' if s is None else str(s) for s in r[1:]]
    print(f'{name:<45} {scores[0]:>3} {scores[1]:>4} {scores[2]:>4} {scores[3]:>4} {scores[4]:>5} {scores[5]:>5}')

print()
print(f'Total repositories processed: {len(rows)}')
scored = [r for r in rows if r[6] is not None]
if scored:
    avg = sum(r[6] for r in scored) / len(scored)
    print(f'Scored: {len(scored)}  |  Average ReproScore: {avg:.1f}/25')

conn.close()
"

echo ""
echo "Done. Full results in output/db/db.sqlite"
