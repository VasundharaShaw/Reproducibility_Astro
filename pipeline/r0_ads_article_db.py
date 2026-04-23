"""
scripts/r0_ads_article_db.py

Fetch high-energy astrophysics articles from NASA ADS that mention
GitHub and Jupyter notebooks. Saves raw results to data/ads_results.json.

This is Step 1 of the data collection pipeline — the astrophysics
equivalent of r0_article_db.py from the biomedical pipeline, which
queried PubMed Central via Biopython's Entrez API.

Run this first, then run r1_ads_article_metadata.py to parse the
results into the database.

Usage:
    cd <project-root>
    export ADS_API_TOKEN=your_token_here
    python scripts/r0_ads_article_db.py

Environment variables:
    ADS_API_TOKEN  (required)
        Your NASA ADS API token.
        Get one free at: https://ui.adsabs.harvard.edu
        → sign in → Account → Settings → API Token

Output:
    data/ads_results.json
"""

import os
import json
import time
import datetime
import requests
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
OUTPUT_FILE  = DATA_DIR / "ads_results.json"

# ── ADS API settings ───────────────────────────────────────────────────────────

ADS_API_TOKEN  = os.environ.get("ADS_API_TOKEN", "")
ADS_SEARCH_URL = "https://api.adsabs.harvard.edu/v1/search/query"

# Records per page — ADS hard limit is 2000, we use 200 to be polite
PAGE_SIZE = 200

# Fields to retrieve for each article.
# These map onto the journal / article / author / repositories DB tables.
FIELDS = [
    "bibcode",      # unique ADS ID  → article.pmid
    "identifier",   # arXiv ID, DOI, etc.
    "title",        # → article.name
    "author",       # list of "Surname, Given"
    "orcid_pub",    # parallel list of ORCIDs
    "pub",          # journal name   → journal.name
    "pubdate",      # → article.published_date
    "doi",          # → article.doi
    "keyword",      # → article.keywords
    "arxiv_class",  # arXiv categories → article.subject
    "abstract",     # full text — mined for GitHub links
    "links_data",   # structured software/data links — mined for GitHub links
    "issn",         # → journal.issn_epub
]

# High-energy astrophysics arXiv categories
HEP_CATEGORIES = [
    "astro-ph.HE",  # high energy astrophysical phenomena
    "hep-ex",       # high energy physics - experiment
    "hep-ph",       # high energy physics - phenomenology
    "hep-th",       # high energy physics - theory
    "hep-lat",      # high energy physics - lattice
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def get_date_range_last_12_months():
    """Return (start_date, end_date) as YYYY-MM-DD strings covering the last 5 years."""
    today = datetime.date.today()
    start = today.replace(year=today.year - 5)
    return start.isoformat(), today.isoformat()


def build_query(start_date, end_date):
    """
    Build the ADS search query string.

    Strategy: search for papers that mention Jupyter/notebooks anywhere
    (abstract OR title OR body), combined with GitHub anywhere
    (abstract OR title OR body OR links).

    We deliberately do NOT require both to appear in the abstract — many
    papers link to GitHub without mentioning it in the abstract text.
    ADS will return the links_data field which we mine for GitHub URLs
    at parse time in r1_ads_article_metadata.py.
    """
    category_filter = " OR ".join(f"arxiv_class:{c}" for c in HEP_CATEGORIES)

    # Search abstract AND title for Jupyter mentions
    jupyter_filter = (
        'abs:"jupyter" OR abs:"ipynb" OR abs:"ipython" OR '
        'title:"jupyter" OR title:"notebook"'
    )

    # GitHub mention anywhere in abstract or title
    # Note: we don't require this — many papers link to GitHub only in
    # the code availability section which isn't indexed in abs:
    # r1_ads_article_metadata.py will mine links_data for GitHub URLs
    github_filter = 'abs:"github" OR title:"github"'

    date_filter = f"pubdate:[{start_date} TO {end_date}]"

    return (
        f"({jupyter_filter}) AND ({github_filter}) "
        f"AND ({category_filter}) "
        f"AND {date_filter}"
    )


def fetch_page(query, start, rows):
    """Fetch one page of results from the ADS API."""
    if not ADS_API_TOKEN:
        raise EnvironmentError(
            "\n[ERROR] ADS_API_TOKEN is not set.\n"
            "Export it before running:\n"
            "    export ADS_API_TOKEN=your_token_here\n"
            "Get a token at: https://ui.adsabs.harvard.edu "
            "→ Account → Settings → API Token"
        )

    headers = {"Authorization": f"Bearer {ADS_API_TOKEN}"}
    params  = {
        "q":    query,
        "fl":   ",".join(FIELDS),
        "rows": rows,
        "start": start,
        "sort": "pubdate desc",
    }

    response = requests.get(ADS_SEARCH_URL, headers=headers, params=params, timeout=30)

    if response.status_code == 401:
        raise EnvironmentError(
            "[ERROR] ADS returned 401 Unauthorized. "
            "Check that your ADS_API_TOKEN is correct."
        )
    if response.status_code == 429:
        print("[ADS] Rate limited — waiting 60s before retrying...")
        time.sleep(60)
        return fetch_page(query, start, rows)
    if response.status_code != 200:
        raise RuntimeError(
            f"[ERROR] ADS API returned HTTP {response.status_code}:\n{response.text}"
        )

    return response.json()


def fetch_all_articles(query):
    """Paginate through all ADS results for the query."""
    # First call to get total count
    print(f"[ADS] Query: {query}\n")
    data  = fetch_page(query, start=0, rows=1)
    total = data["response"]["numFound"]
    print(f"[ADS] Total articles found: {total}")

    if total == 0:
        print("[ADS] No articles found. Check your query or date range.")
        return []

    articles = []
    start    = 0
    while start < total:
        end = min(start + PAGE_SIZE, total)
        print(f"[ADS] Fetching records {start + 1}–{end} of {total}...")
        data = fetch_page(query, start=start, rows=PAGE_SIZE)
        articles.extend(data["response"]["docs"])
        start += PAGE_SIZE
        if start < total:
            time.sleep(1)   # be polite to the API

    print(f"[ADS] Fetched {len(articles)} articles total.")
    return articles


# ── Main ───────────────────────────────────────────────────────────────────────

def get_publications_from_ads():
    """
    Fetch articles from NASA ADS and save to data/ads_results.json.

    Equivalent of get_publications_from_db() in r0_article_db.py,
    which fetched from PMC and saved to pmc.xml.
    """
    start_date, end_date = get_date_range_last_12_months()
    print(f"[ADS] Date range: {start_date} to {end_date}")

    query    = build_query(start_date, end_date)
    articles = fetch_all_articles(query)

    output = {
        "query":      query,
        "start_date": start_date,
        "end_date":   end_date,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "total":      len(articles),
        "articles":   articles,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[ADS] Saved {len(articles)} articles to {OUTPUT_FILE}")


def main():
    get_publications_from_ads()


if __name__ == "__main__":
    main()
