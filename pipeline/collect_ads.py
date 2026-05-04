"""
pipeline/collect_ads.py

Fetch astrophysics articles from NASA ADS that mention Jupyter notebooks
(with or without a hosting platform), classify each article by notebook
category, and populate data/db.sqlite.

Notebook categories (stored in article.notebook_category):
    jupyter_only             — Jupyter/ipynb indicators, no recognised host
    jupyter_with_github      — Jupyter/ipynb + GitHub
    jupyter_with_zenodo      — Jupyter/ipynb + Zenodo
    jupyter_with_personal    — Jupyter/ipynb + personal/other website
    jupyter_with_github_zenodo — Jupyter/ipynb + both GitHub and Zenodo

Creates four tables if they don't exist:
    journal          — one row per publication venue
    article          — one row per paper
    author           — one row per author
    repositories     — one row per extracted repo/host URL
    notebook_mentions — one row per in-text notebook mention (populated by
                        extract_mentions.py, schema created here)

Usage:
    export ADS_API_TOKEN=your_ads_token_here
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
    "abstract",     # mined for host links
    "links_data",   # structured links    → mined for host links
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

# ── Recognised hosting domains ─────────────────────────────────────────────────

GITHUB_PATTERNS  = ["github.com", "github.io"]
ZENODO_PATTERNS  = ["zenodo.org", "zenodo"]
PERSONAL_DOMAINS = ["gitlab.com", "bitbucket.org", "figshare.com",
                    "mybinder.org", "binder.", "colab.research.google.com",
                    "osf.io", "dataverse", "huggingface.co"]

# ── Database setup ─────────────────────────────────────────────────────────────

def ensure_tables(conn):
    """Create all tables including notebook_mentions."""
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
            notebook_category   TEXT,
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

        CREATE TABLE IF NOT EXISTS repositories (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id         INTEGER REFERENCES article(id),
            domain             TEXT,
            repository         TEXT,
            host_type          TEXT,
            notebooks_count    INTEGER DEFAULT 0,
            setups_count       INTEGER DEFAULT 0,
            requirements_count INTEGER DEFAULT 0,
            processed          INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS notebook_mentions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id    INTEGER NOT NULL,
            mention_text  TEXT,
            context       TEXT,
            section       TEXT,
            link_form     TEXT,
            url           TEXT,
            host          TEXT,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (article_id) REFERENCES article(id)
        );
    """)
    conn.commit()
    print("[DB] Tables ready: journal, article, author, repositories, notebook_mentions.")


# ── Categorisation ─────────────────────────────────────────────────────────────

def classify_notebook_category(record):
    """
    Determine notebook_category from the ADS record text (abstract +
    identifier list + links_data URLs).

    Returns one of:
        jupyter_only
        jupyter_with_github
        jupyter_with_zenodo
        jupyter_with_personal
        jupyter_with_github_zenodo
    """
    text_blob = " ".join([
        record.get("abstract", "") or "",
        " ".join(record.get("identifier", []) or []),
    ]).lower()

    # Also fold in any URLs from links_data
    try:
        entries = record.get("links_data", "") or ""
        if isinstance(entries, str):
            entries = json.loads(entries)
        for entry in entries:
            if isinstance(entry, dict):
                text_blob += " " + entry.get("url", "").lower()
            elif isinstance(entry, str):
                text_blob += " " + entry.lower()
    except (json.JSONDecodeError, TypeError):
        pass

    has_github   = any(p in text_blob for p in GITHUB_PATTERNS)
    has_zenodo   = any(p in text_blob for p in ZENODO_PATTERNS)
    has_personal = any(p in text_blob for p in PERSONAL_DOMAINS)

    if has_github and has_zenodo:
        return "jupyter_with_github_zenodo"
    if has_github:
        return "jupyter_with_github"
    if has_zenodo:
        return "jupyter_with_zenodo"
    if has_personal:
        return "jupyter_with_personal"
    return "jupyter_only"


# ── URL extraction helpers ─────────────────────────────────────────────────────

def preprocess_url(url):
    """Normalise a GitHub URL to https://github.com/<owner>/<repo> or return None."""
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


def detect_host_type(url):
    """Return a host_type string for a given URL."""
    url_lower = url.lower()
    if "github.com" in url_lower or "github.io" in url_lower:
        return "github"
    if "zenodo.org" in url_lower:
        return "zenodo"
    if "gitlab.com" in url_lower:
        return "gitlab"
    if "bitbucket.org" in url_lower:
        return "bitbucket"
    if "figshare.com" in url_lower:
        return "figshare"
    if "mybinder.org" in url_lower or "binder." in url_lower:
        return "binder"
    if "colab.research.google.com" in url_lower:
        return "colab"
    if "osf.io" in url_lower:
        return "osf"
    if "dataverse" in url_lower:
        return "dataverse"
    if "huggingface.co" in url_lower:
        return "huggingface"
    return "personal_site"


def extract_all_links(record):
    """
    Extract all URLs from an ADS record (abstract + links_data + identifiers).
    Returns list of (url, host_type) tuples, deduplicated.
    """
    raw = []

    abstract = record.get("abstract", "") or ""
    for m in re.findall(r"https?://[^\s\]\)\>\"\']+", abstract):
        raw.append(m)

    try:
        entries = record.get("links_data", "") or ""
        if isinstance(entries, str):
            entries = json.loads(entries)
        for entry in entries:
            if isinstance(entry, dict):
                url = entry.get("url", "")
            elif isinstance(entry, str):
                try:
                    entry = json.loads(entry)
                    url = entry.get("url", "") if isinstance(entry, dict) else entry
                except (json.JSONDecodeError, TypeError):
                    url = entry
            else:
                continue
            if url:
                raw.append(url)
    except (json.JSONDecodeError, TypeError):
        pass

    for ident in record.get("identifier", []):
        if re.match(r"https?://", ident):
            raw.append(ident)

    seen, result = set(), []
    for url in raw:
        url = re.sub(r"[\(\) ;]", "", url)
        if not url or url in seen:
            continue
        seen.add(url)
        result.append((url, detect_host_type(url)))
    return result


def extract_github_links(record):
    """Return normalised GitHub repo URLs only (for repositories table)."""
    seen, result = set(), []
    for url, host_type in extract_all_links(record):
        if host_type != "github":
            continue
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
    """Insert article row. Returns (article_id, repo_links, all_links) or None if duplicate."""
    cur    = conn.cursor()
    titles = record.get("title", [])
    title  = titles[0] if titles else None
    if not title:
        return None

    cur.execute("SELECT id FROM article WHERE name = ?", (title,))
    if cur.fetchone():
        return None

    repo_links        = extract_github_links(record)
    all_links         = extract_all_links(record)
    doi_list          = record.get("doi", [])
    pubdate           = re.sub(r"-00", "-01", record.get("pubdate", "") or "")
    keywords          = ";".join(record.get("keyword", []))      or None
    subject           = ";".join(record.get("arxiv_class", [])) or None
    repositories_str  = ";".join(repo_links) if repo_links else None
    notebook_category = classify_notebook_category(record)

    cur.execute(
        """INSERT INTO article
               (journal_id, name, pmid, pmc, doi, subject,
                published_date, keywords, repositories, notebook_category)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (journal_id, title,
         record.get("bibcode"),
         extract_arxiv_id(record.get("identifier", [])),
         doi_list[0] if doi_list else None,
         subject, pubdate, keywords, repositories_str, notebook_category),
    )
    conn.commit()
    article_id = cur.lastrowid
    print(f"  [ARTICLE] [{notebook_category}] {title[:70]}")
    return article_id, repo_links, all_links


def create_authors(conn, record, article_id):
    cur     = conn.cursor()
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


def create_repositories(conn, article_id, repo_links, all_links):
    """
    Insert all extracted URLs into repositories table with host_type.
    GitHub repos use normalised path; others use the raw URL as repository.
    No GitHub API check — discovery happens at pipeline run time.
    """
    cur      = conn.cursor()
    inserted = 0

    # GitHub repos (normalised)
    for url in repo_links:
        repo_path = re.sub(r"https?://github\.com/", "", url)
        cur.execute("SELECT id FROM repositories WHERE repository = ?", (repo_path,))
        if cur.fetchone():
            continue
        cur.execute(
            """INSERT INTO repositories
                   (article_id, domain, repository, host_type,
                    notebooks_count, setups_count, requirements_count, processed)
               VALUES (?, 'github.com', ?, 'github', 0, 0, 0, 0)""",
            (article_id, repo_path),
        )
        inserted += 1

    # Non-GitHub links (zenodo, personal, etc.)
    for url, host_type in all_links:
        if host_type == "github":
            continue  # already handled above
        domain = urlparse(url).netloc or host_type
        cur.execute("SELECT id FROM repositories WHERE repository = ?", (url,))
        if cur.fetchone():
            continue
        cur.execute(
            """INSERT INTO repositories
                   (article_id, domain, repository, host_type,
                    notebooks_count, setups_count, requirements_count, processed)
               VALUES (?, ?, ?, ?, 0, 0, 0, 0)""",
            (article_id, domain, url, host_type),
        )
        inserted += 1

    conn.commit()
    return inserted


# ── ADS fetch ──────────────────────────────────────────────────────────────────

def get_date_range():
    today = datetime.date.today()
    start = today.replace(year=today.year - 5)
    return start.isoformat(), today.isoformat()


def build_query(start_date, end_date):
    category_filter = " OR ".join(f"arxiv_class:{c}" for c in ASTRO_CATEGORIES)
    jupyter_filter  = (
        'abs:"jupyter" OR abs:"ipynb" OR abs:".ipynb" OR '
        'abs:"jupyter notebook" OR abs:"jupyter lab" OR '
        'title:"jupyter" OR title:"ipynb" OR title:"jupyter notebook" OR '
        'title:"jupyter lab" OR '
        'body:"jupyter" OR body:"ipynb" OR body:".ipynb" OR '
        'body:"jupyter notebook" OR body:"jupyter lab"'
    )
    date_filter = f"pubdate:[{start_date} TO {end_date}]"
    return (
        f"({jupyter_filter}) AND ({category_filter}) AND {date_filter}"
    )


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
    category_counts = {}

    for record in articles:
        journal_id = get_or_create_journal(conn, record)
        result     = create_article(conn, record, journal_id)
        if result is None:
            skipped += 1
            continue
        article_id, repo_links, all_links = result
        created += 1

        # tally categories
        cur = conn.cursor()
        cur.execute("SELECT notebook_category FROM article WHERE id = ?", (article_id,))
        cat = cur.fetchone()[0]
        category_counts[cat] = category_counts.get(cat, 0) + 1

        create_authors(conn, record, article_id)
        repos += create_repositories(conn, article_id, repo_links, all_links)

    conn.close()

    print(f"\n[DONE]")
    print(f"  Articles created : {created}")
    print(f"  Articles skipped : {skipped} (already in DB)")
    print(f"  Repos/links inserted : {repos}")
    print(f"\n  Category breakdown:")
    for cat, count in sorted(category_counts.items()):
        print(f"    {cat:<35} {count}")


if __name__ == "__main__":
    main()
