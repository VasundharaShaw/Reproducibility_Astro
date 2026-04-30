"""
pipeline/collect_ads.py

Fetch high-energy astrophysics articles from NASA ADS that mention
GitHub and Jupyter notebooks, and populate data/db.sqlite directly.

Creates four tables if they don't exist:
    journal      — one row per publication venue
    article      — one row per paper
    author       — one row per author
    repositories — one row per GitHub repo found (used by run.sh batch mode)

Usage:
    export ADS_API_TOKEN=your_token_here
    python3 pipeline/collect_ads.py

Or via the wrapper:
    bash collect.sh
"""

import os
import re
import json
import time
import sqlite3
import datetime
import requests
from pathlib import Path
from urllib.parse import urlparse

# ── Paths ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILE      = PROJECT_ROOT / "data" / "db.sqlite"

# ── ADS API settings ───────────────────────────────────────────────────────────

ADS_API_TOKEN  = os.environ.get("ADS_API_TOKEN", "")
ADS_SEARCH_URL = "https://api.adsabs.harvard.edu/v1/search/query"
PAGE_SIZE      = 200

FIELDS = [
    "bibcode",      # unique ADS ID       → article.pmid
    "identifier",   # arXiv ID, DOI, etc. → article.pmc
    "title",        #                     → article.name
    "author",       # "Surname, Given"
    "orcid_pub",    # parallel ORCID list
    "pub",          # journal name        → journal.name
    "pubdate",      #                     → article.published_date
    "doi",          #                     → article.doi
    "keyword",      #                     → article.keywords
    "arxiv_class",  # arXiv categories    → article.subject
    "abstract",     # mined for GitHub links
    "links_data",   # structured links    → mined for GitHub links
    "issn",         #                     → journal.issn_epub
]

ASTRO_CATEGORIES = [
    "astro-ph.HE",  # high energy astrophysical phenomena
    "astro-ph.GA",  # astrophysics of galaxies
    "astro-ph.CO",  # cosmology and nongalactic astrophysics
    "astro-ph.EP",  # earth and planetary astrophysics
    "astro-ph.IM",  # instrumentation and methods for astrophysics
    "astro-ph.SR",  # solar and stellar astrophysics
    "hep-ex",       # high energy physics - experiment
    "hep-ph",       # high energy physics - phenomenology
    "hep-th",       # high energy physics - theory
    "hep-lat",      # high energy physics - lattice
]

# ── Database setup ─────────────────────────────────────────────────────────────

def ensure_tables(conn):
    """Create article/journal/author tables and add article_id to repositories."""
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS journal (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT,
            nlm_ta         TEXT,
            iso_abbrev     TEXT,
            issn_epub      TEXT,
            publisher_name TEXT,
            publisher_loc  TEXT
        );

        CREATE TABLE IF NOT EXISTS article (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_id          INTEGER,
            name                TEXT,
            pmid                TEXT,
            pmc                 TEXT,
            publisher_id        TEXT,
            doi                 TEXT,
            subject             TEXT,
            published_date      TEXT,
            received_date       TEXT,
            accepted_date       TEXT,
            license_type        TEXT,
            copyright_statement TEXT,
            keywords            TEXT,
            repositories        TEXT,
            FOREIGN KEY (journal_id) REFERENCES journal(id)
        );

        CREATE TABLE IF NOT EXISTS author (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id  INTEGER,
            name        TEXT,
            given_names TEXT,
            orcid       TEXT,
            email       TEXT,
            FOREIGN KEY (article_id) REFERENCES article(id)
        );
    """)

    # Add article_id to repositories only if missing
    cur.execute("PRAGMA table_info(repositories);")
    if "article_id" not in [row[1] for row in cur.fetchall()]:
        cur.execute(
            "ALTER TABLE repositories ADD COLUMN article_id INTEGER "
            "REFERENCES article(id);"
        )
        print("[DB] Added article_id column to repositories.")

    conn.commit()
    print("[DB] Tables ready: journal, article, author, repositories.")


# ── GitHub link extraction ─────────────────────────────────────────────────────

def preprocess_url(url):
    """Normalise a URL to https://github.com/<owner>/<repo> or return None."""
    url = re.sub(r"[\(\) ]", "", url)
    url = re.sub(r";.*", "", url)
    if re.match(r"(.*)github\.com/(.*)/(.+)", url):
        url = url.replace("www.", "")
        if url.startswith("github"):
            url = "https://" + url
        parse = urlparse(url)
        if parse.scheme in ("", "http"):
            parse = parse._replace(scheme="https")
        if parse.netloc == "github.com":
            repo = parse.path[1:]
            if repo.endswith(".git"):
                repo = repo[:-4]
            parts = repo.split("/")[:2]
            if not parts or parts[0] in ("orgs", "collections", "topics", "features"):
                return None
            repo = "/".join(parts).rstrip(".")
            return f"https://github.com/{repo}"
    return None


def extract_github_links(record):
    """Mine all GitHub repo URLs from an ADS record."""
    raw = []

    # Abstract text
    for m in re.findall(r"https?://[^\s\]\)\>\"\']+", record.get("abstract", "") or ""):
        raw.append(m)
    for m in re.findall(r"github\.com/[^\s\]\)\>\"\']+", record.get("abstract", "") or ""):
        raw.append(m)

    # Structured links_data field
    try:
        entries = record.get("links_data", "") or ""
        if isinstance(entries, str):
            entries = json.loads(entries)
        for entry in entries:
            # ADS returns links_data as either dicts or raw strings
            if isinstance(entry, dict):
                url = entry.get("url", "")
            elif isinstance(entry, str):
                # try to parse as JSON, otherwise treat as raw URL
                try:
                    entry = json.loads(entry)
                    url = entry.get("url", "") if isinstance(entry, dict) else entry
                except (json.JSONDecodeError, TypeError):
                    url = entry
            else:
                continue
            if "github" in url.lower():
                raw.append(url)
    except (json.JSONDecodeError, TypeError):
        pass

    # Identifier list
    for ident in record.get("identifier", []):
        if "github" in ident.lower():
            raw.append(ident)

    # Deduplicate and normalise
    seen, result = set(), []
    for url in raw:
        canonical = preprocess_url(url)
        if canonical and canonical not in seen:
            if re.match(r"https?://github\.com/(.+)/(.+)", canonical):
                seen.add(canonical)
                result.append(canonical)
    return result


def extract_arxiv_id(identifiers):
    for ident in (identifiers or []):
        if ident.lower().startswith("arxiv:"):
            return ident[6:]
        if re.match(r"^\d{4}\.\d{4,5}$", ident):
            return ident
    return None


# ── DB write helpers ───────────────────────────────────────────────────────────

def get_or_create_journal(conn, record):
    cur  = conn.cursor()
    name = record.get("pub") or "arXiv preprint"
    cur.execute("SELECT id FROM journal WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    issns = record.get("issn", [])
    cur.execute(
        "INSERT INTO journal (name, issn_epub) VALUES (?, ?)",
        (name, issns[0] if issns else None),
    )
    conn.commit()
    print(f"  [JOURNAL] {name}")
    return cur.lastrowid


def create_article(conn, record, journal_id):
    """Insert article row. Returns (article_id, repo_links) or None if duplicate."""
    cur    = conn.cursor()
    titles = record.get("title", [])
    title  = titles[0] if titles else None
    if not title:
        return None

    cur.execute("SELECT id FROM article WHERE name = ?", (title,))
    if cur.fetchone():
        return None

    repo_links   = extract_github_links(record)
    doi_list     = record.get("doi", [])
    pubdate      = re.sub(r"-00", "-01", record.get("pubdate", "") or "")
    keywords     = ";".join(record.get("keyword", []))      or None
    subject      = ";".join(record.get("arxiv_class", [])) or None
    repositories = ";".join(repo_links) if repo_links else None

    cur.execute(
        """INSERT INTO article
               (journal_id, name, pmid, pmc, doi, subject,
                published_date, keywords, repositories)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (journal_id, title,
         record.get("bibcode"),
         extract_arxiv_id(record.get("identifier", [])),
         doi_list[0] if doi_list else None,
         subject, pubdate, keywords, repositories),
    )
    conn.commit()
    article_id = cur.lastrowid
    print(f"  [ARTICLE] {title[:75]}")
    return article_id, repo_links


def create_authors(conn, record, article_id):
    cur    = conn.cursor()
    authors = record.get("author", [])
    orcids  = record.get("orcid_pub", [])
    rows = []
    for i, name in enumerate(authors):
        parts  = name.split(",", 1)
        orcid  = orcids[i] if i < len(orcids) else None
        if orcid == "-":
            orcid = None
        rows.append((article_id, parts[0].strip(),
                     parts[1].strip() if len(parts) > 1 else None, orcid))
    cur.executemany(
        "INSERT INTO author (article_id, name, given_names, orcid) VALUES (?,?,?,?)",
        rows,
    )
    conn.commit()


def create_repositories(conn, article_id, repo_links):
    cur      = conn.cursor()
    inserted = 0
    for url in repo_links:
        repo_path = re.sub(r"https?://github\.com/", "", url)
        cur.execute("SELECT id FROM repositories WHERE repository = ?", (repo_path,))
        if cur.fetchone():
            continue
        cur.execute(
            """INSERT INTO repositories
                   (article_id, domain, repository,
                    notebooks_count, setups_count, requirements_count, processed)
               VALUES (?, 'github.com', ?, 0, 0, 0, 0)""",
            (article_id, repo_path),
        )
        inserted += 1
    conn.commit()
    return inserted


# ── ADS fetch ──────────────────────────────────────────────────────────────────

def get_date_range():
    today = datetime.date.today()
    start = today.replace(year=today.year - 15)
    return start.isoformat(), today.isoformat()

##### Collecting repos that mention both Github and jupyter 


def build_query(start_date, end_date):
    category_filter = " OR ".join(f"arxiv_class:{c}" for c in ASTRO_CATEGORIES)
    jupyter_filter  = (
        'abs:"jupyter" OR abs:"ipynb" OR abs:"ipython" OR '
        'title:"jupyter" OR title:"notebook"'
    )
    github_filter   = 'abs:"github" OR title:"github"'
    date_filter     = f"pubdate:[{start_date} TO {end_date}]"
    return (
        f"({jupyter_filter}) AND ({github_filter}) "
        f"AND ({category_filter}) AND {date_filter}"
    )

##### Collecting repos that mention ONLY Github and  NOT jupyter 
# def build_query(start_date, end_date):
#     category_filter = " OR ".join(f"arxiv_class:{c}" for c in ASTRO_CATEGORIES)
#     github_filter   = 'abs:"github" OR title:"github"'
#     date_filter     = f"pubdate:[{start_date} TO {end_date}]"
#     return f"({github_filter}) AND ({category_filter}) AND {date_filter}"

def fetch_page(query, start, rows):
    if not ADS_API_TOKEN:
        raise EnvironmentError(
            "[ERROR] ADS_API_TOKEN is not set.\n"
            "Run: export ADS_API_TOKEN=your_token_here"
        )
    headers  = {"Authorization": f"Bearer {ADS_API_TOKEN}"}
    params   = {"q": query, "fl": ",".join(FIELDS),
                "rows": rows, "start": start, "sort": "pubdate desc"}
    response = requests.get(ADS_SEARCH_URL, headers=headers,
                            params=params, timeout=30)
    if response.status_code == 401:
        raise EnvironmentError("[ERROR] ADS API: 401 Unauthorized. Check your token.")
    if response.status_code == 429:
        print("[ADS] Rate limited — waiting 60s...")
        time.sleep(60)
        return fetch_page(query, start, rows)
    if response.status_code != 200:
        raise RuntimeError(f"[ERROR] ADS API: HTTP {response.status_code}\n{response.text}")
    return response.json()


def fetch_all_articles(query):
    print(f"[ADS] Query: {query}\n")
    total = fetch_page(query, 0, 1)["response"]["numFound"]
    print(f"[ADS] Total articles found: {total}")
    if total == 0:
        return []
    articles, start = [], 0
    while start < total:
        end = min(start + PAGE_SIZE, total)
        print(f"[ADS] Fetching {start + 1}–{end} of {total}...")
        articles.extend(fetch_page(query, start, PAGE_SIZE)["response"]["docs"])
        start += PAGE_SIZE
        if start < total:
            time.sleep(1)
    print(f"[ADS] Fetched {len(articles)} articles.")
    return articles


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    start_date, end_date = get_date_range()
    print(f"[ADS] Date range: {start_date} to {end_date}\n")

    query    = build_query(start_date, end_date)
    articles = fetch_all_articles(query)

    if not articles:
        return

    print(f"\n[DB] Writing to {DB_FILE}\n")
    conn = sqlite3.connect(DB_FILE)
    ensure_tables(conn)

    created  = 0
    skipped  = 0
    repos    = 0

    for record in articles:
        journal_id = get_or_create_journal(conn, record)
        result     = create_article(conn, record, journal_id)
        if result is None:
            skipped += 1
            continue
        article_id, repo_links = result
        created += 1
        create_authors(conn, record, article_id)
        repos += create_repositories(conn, article_id, repo_links)

    conn.close()

    print(f"\n[DONE]")
    print(f"  Articles created : {created}")
    print(f"  Articles skipped : {skipped} (already in DB)")
    print(f"  Repos inserted   : {repos}")


if __name__ == "__main__":
    main()
