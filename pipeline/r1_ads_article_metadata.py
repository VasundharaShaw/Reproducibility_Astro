"""
scripts/r1_ads_article_metadata.py

Parse data/ads_results.json (produced by r0_ads_article_db.py) and
populate four tables in data/db.sqlite:

    journal      — one row per unique publication venue
    article      — one row per paper
    author       — one row per author (linked to article)
    repositories — one row per GitHub repo found (linked to article)
                   These are the rows the pipeline reads in batch mode.

This is Step 2 of the data collection pipeline — the astrophysics
equivalent of r1_article_metadata.py from the biomedical pipeline,
which parsed pmc.xml (JATS/XML from PubMed Central).

Field mapping  ADS → DB
    bibcode          → article.pmid   (unique ADS identifier)
    arXiv ID         → article.pmc    (arXiv = astro equivalent of PMC)
    title            → article.name
    doi              → article.doi
    pubdate          → article.published_date
    keyword          → article.keywords
    arxiv_class      → article.subject
    pub              → journal.name
    issn             → journal.issn_epub
    GitHub links     → article.repositories  (mined from abstract + links_data)

Usage:
    cd <project-root>
    python scripts/r1_ads_article_metadata.py

Run after r0_ads_article_db.py has produced data/ads_results.json.
"""

import json
import re
import sqlite3
import os
from pathlib import Path
from urllib.parse import urlparse

# ── Paths ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
ADS_JSON_FILE = PROJECT_ROOT / "data" / "ads_results.json"
DB_FILE       = PROJECT_ROOT / "data" / "db.sqlite"

# ── Database setup ─────────────────────────────────────────────────────────────

CREATE_JOURNAL_TABLE = """
CREATE TABLE IF NOT EXISTS journal (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT,
    nlm_ta       TEXT,
    iso_abbrev   TEXT,
    issn_epub    TEXT,
    publisher_name TEXT,
    publisher_loc  TEXT
);
"""

CREATE_ARTICLE_TABLE = """
CREATE TABLE IF NOT EXISTS article (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id            INTEGER,
    name                  TEXT,
    pmid                  TEXT,
    pmc                   TEXT,
    publisher_id          TEXT,
    doi                   TEXT,
    subject               TEXT,
    published_date        TEXT,
    received_date         TEXT,
    accepted_date         TEXT,
    license_type          TEXT,
    copyright_statement   TEXT,
    keywords              TEXT,
    repositories          TEXT,
    FOREIGN KEY (journal_id) REFERENCES journal(id)
);
"""

CREATE_AUTHOR_TABLE = """
CREATE TABLE IF NOT EXISTS author (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id   INTEGER,
    name         TEXT,
    given_names  TEXT,
    orcid        TEXT,
    email        TEXT,
    FOREIGN KEY (article_id) REFERENCES article(id)
);
"""

# The repositories table already exists in data/db.sqlite.
# We add article_id as a new column if it isn't there yet,
# so repos fetched from ADS are linked back to their article.
ADD_ARTICLE_ID_COLUMN = """
ALTER TABLE repositories ADD COLUMN article_id INTEGER
    REFERENCES article(id);
"""


def ensure_tables(conn):
    """
    Create the new tables if they don't exist, and add article_id
    to the existing repositories table if it's missing.

    Safe to run multiple times — all statements use IF NOT EXISTS.
    """
    cur = conn.cursor()
    cur.execute(CREATE_JOURNAL_TABLE)
    cur.execute(CREATE_ARTICLE_TABLE)
    cur.execute(CREATE_AUTHOR_TABLE)

    # Add article_id to repositories only if not already present
    cur.execute("PRAGMA table_info(repositories);")
    columns = [row[1] for row in cur.fetchall()]
    if "article_id" not in columns:
        cur.execute(ADD_ARTICLE_ID_COLUMN)
        print("[DB] Added article_id column to repositories table.")

    conn.commit()
    print("[DB] Tables ensured: journal, article, author, repositories.")


# ── GitHub link extraction ─────────────────────────────────────────────────────

def preprocess_url(url):
    """
    Normalise a raw URL to: https://github.com/<owner>/<repo>
    Returns None if not a valid GitHub repo link.
    Mirrors preprocess_url() in r1_article_metadata.py exactly.
    """
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
            repo = "/".join(parts)
            if repo.endswith("."):
                repo = repo[:-1]
            return f"https://github.com/{repo}"

    elif re.match(r"https?://nbviewer\..*\.org/github/\w+/\w+", url):
        parse = urlparse(url)
        parts = parse.path.split("/")
        repo  = parts[2] + "/" + parts[3]
        return f"https://github.com/{repo}"

    return None


def extract_raw_links_from_text(text):
    """Find all candidate GitHub URLs in a block of text."""
    if not text:
        return []
    raw  = re.findall(r"https?://[^\s\]\)\>\"\']+", text)
    raw += re.findall(r"github\.com/[^\s\]\)\>\"\']+", text)
    return raw


def extract_raw_links_from_links_data(links_data):
    """Extract GitHub URLs from the ADS structured links_data field."""
    if not links_data:
        return []
    raw = []
    try:
        entries = json.loads(links_data) if isinstance(links_data, str) else links_data
        for entry in entries:
            url = entry.get("url", "")
            if "github" in url.lower():
                raw.append(url)
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return raw


def get_processed_links(raw_links):
    """Deduplicate and normalise raw URLs into canonical GitHub repo URLs."""
    seen   = set()
    result = []
    for url in raw_links:
        canonical = preprocess_url(url)
        if canonical and canonical not in seen:
            if re.match(r"https?://github\.com/(.+)/(.+)", canonical):
                seen.add(canonical)
                result.append(canonical)
    return result


def extract_all_github_links(record):
    """
    Collect GitHub links from all fields of an ADS record:
      1. abstract text
      2. links_data (structured software/data links)
      3. identifier list (occasionally contains GitHub URLs)

    Equivalent of extract_github_links() in r1_article_metadata.py,
    which searched multiple XML XPath expressions across the PMC article.
    """
    raw = []
    raw += extract_raw_links_from_text(record.get("abstract", ""))
    raw += extract_raw_links_from_links_data(record.get("links_data", ""))
    for ident in record.get("identifier", []):
        if "github" in ident.lower():
            raw.append(ident)
    return get_processed_links(raw)


# ── arXiv ID helper ────────────────────────────────────────────────────────────

def extract_arxiv_id(identifiers):
    """
    Pull the arXiv ID from the ADS identifier list.
    ADS stores it as "arXiv:2301.12345" or bare "2301.12345".
    """
    for ident in (identifiers or []):
        if ident.lower().startswith("arxiv:"):
            return ident[6:]
        if re.match(r"^\d{4}\.\d{4,5}$", ident):
            return ident
    return None


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_or_create_journal(conn, record):
    """
    Return the journal id, creating the row if it doesn't exist.
    Mirrors create_journal_entry() in r1_article_metadata.py.
    """
    cur          = conn.cursor()
    journal_name = record.get("pub") or "arXiv preprint"
    issns        = record.get("issn", [])
    issn         = issns[0] if issns else None

    cur.execute("SELECT id FROM journal WHERE name = ?", (journal_name,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        "INSERT INTO journal (name, issn_epub) VALUES (?, ?)",
        (journal_name, issn),
    )
    conn.commit()
    journal_id = cur.lastrowid
    print(f"  [JOURNAL] Created id={journal_id}  {journal_name}")
    return journal_id


def create_article(conn, record, journal_id):
    """
    Insert an article row if it doesn't already exist.
    Returns the new article id, or None if it was a duplicate.
    Mirrors create_article_entry() in r1_article_metadata.py.
    """
    cur    = conn.cursor()
    titles = record.get("title", [])
    title  = titles[0] if titles else None
    if not title:
        return None

    # Deduplication — same approach as original
    cur.execute("SELECT id FROM article WHERE name = ?", (title,))
    if cur.fetchone():
        return None

    bibcode  = record.get("bibcode")
    arxiv_id = extract_arxiv_id(record.get("identifier", []))
    doi_list = record.get("doi", [])
    doi      = doi_list[0] if doi_list else None

    # ADS pubdate can be "YYYY-MM-00" — normalise unknowns to 01
    pubdate = re.sub(r"-00", "-01", record.get("pubdate", "") or "")

    keywords     = ";".join(record.get("keyword", []))      or None
    subject      = ";".join(record.get("arxiv_class", [])) or None
    repo_links   = extract_all_github_links(record)
    repositories = ";".join(repo_links) if repo_links else None

    cur.execute(
        """
        INSERT INTO article
            (journal_id, name, pmid, pmc, doi, subject,
             published_date, keywords, repositories)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (journal_id, title, bibcode, arxiv_id, doi,
         subject, pubdate, keywords, repositories),
    )
    conn.commit()
    article_id = cur.lastrowid
    print(f"  [ARTICLE] Created id={article_id}  {title[:70]}")
    return article_id, repo_links


def create_authors(conn, record, article_id):
    """
    Insert one author row per author in the ADS record.
    Mirrors create_authors_entry() in r1_article_metadata.py.
    """
    cur     = conn.cursor()
    authors = record.get("author", [])
    orcids  = record.get("orcid_pub", [])

    rows = []
    for i, author_name in enumerate(authors):
        parts   = author_name.split(",", 1)
        surname = parts[0].strip()
        given   = parts[1].strip() if len(parts) > 1 else None
        orcid   = orcids[i] if i < len(orcids) else None
        if orcid == "-":
            orcid = None
        rows.append((article_id, surname, given, orcid))

    cur.executemany(
        "INSERT INTO author (article_id, name, given_names, orcid) VALUES (?,?,?,?)",
        rows,
    )
    conn.commit()


def create_repositories(conn, article_id, repo_links):
    """
    Insert a row into the repositories table for each GitHub repo
    found in the article. These rows are what the pipeline reads
    in batch mode (Mode 2).

    We store only the owner/repo path (no https://github.com/ prefix)
    to match how existing rows are stored in this table.
    Skips repos that are already present.
    """
    cur = conn.cursor()
    inserted = 0
    for url in repo_links:
        # Strip the https://github.com/ prefix → owner/repo
        repo_path = re.sub(r"https?://github\.com/", "", url)

        cur.execute(
            "SELECT id FROM repositories WHERE repository = ?", (repo_path,)
        )
        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO repositories
                (article_id, domain, repository, notebooks_count,
                 setups_count, requirements_count, processed)
            VALUES (?, 'github.com', ?, 0, 0, 0, 0)
            """,
            (article_id, repo_path),
        )
        inserted += 1

    conn.commit()
    return inserted


# ── Top-level parser ───────────────────────────────────────────────────────────

def get_articles_metadata():
    """
    Parse ads_results.json and populate journal / article / author /
    repositories tables in data/db.sqlite.

    Equivalent of get_articles_metadata() in r1_article_metadata.py.
    """
    if not ADS_JSON_FILE.exists():
        raise FileNotFoundError(
            f"{ADS_JSON_FILE} not found.\n"
            "Run scripts/r0_ads_article_db.py first."
        )

    with open(ADS_JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("articles", [])
    print(f"[META] Processing {len(records)} ADS records from {ADS_JSON_FILE.name}")
    print(f"[META] Writing to {DB_FILE}\n")

    conn = sqlite3.connect(DB_FILE)
    ensure_tables(conn)

    articles_created = 0
    articles_skipped = 0
    repos_inserted   = 0

    for record in records:
        journal_id = get_or_create_journal(conn, record)
        result     = create_article(conn, record, journal_id)

        if result is None:
            articles_skipped += 1
            continue

        article_id, repo_links = result
        articles_created += 1

        create_authors(conn, record, article_id)
        repos_inserted += create_repositories(conn, article_id, repo_links)

    conn.close()

    print(f"\n[META] Done.")
    print(f"  Articles created : {articles_created}")
    print(f"  Articles skipped : {articles_skipped} (already in DB)")
    print(f"  Repos inserted   : {repos_inserted}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    get_articles_metadata()


if __name__ == "__main__":
    main()
