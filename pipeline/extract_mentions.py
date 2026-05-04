"""
pipeline/extract_mentions.py

For each article in data/db.sqlite that has an arXiv ID, fetch the LaTeX
source tarball from arXiv, parse all .tex files, and extract every mention
of Jupyter/notebook indicators into the notebook_mentions table.

Also updates article.notebook_category if full-text evidence reveals a
hosting platform not visible in the abstract.

Idempotent: articles that already have rows in notebook_mentions are skipped.

Extracted fields per mention:
    mention_text  — the matched keyword/phrase
    context       — ±200 chars surrounding the mention
    section       — nearest LaTeX section heading, or heuristic label
    link_form     — url | doi | footnote | plain_text
    url           — adjacent URL if found, else None
    host          — github | zenodo | gitlab | personal_site | none | …

Usage:
    python3 pipeline/extract_mentions.py

Or via the wrapper:
    bash mentions.sh
"""

import argparse
import io
import os
import re
import sqlite3
import tarfile
import time
import gzip
import requests
from pathlib import Path
from urllib.parse import urlparse

# ── Paths ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILE      = PROJECT_ROOT / "data" / "db.sqlite"

# ── arXiv settings ─────────────────────────────────────────────────────────────

ARXIV_EPRINT_URL  = "https://arxiv.org/e-print/{arxiv_id}"
REQUEST_DELAY_SEC = 3          # arXiv bulk-access courtesy limit
REQUEST_TIMEOUT   = 30

# ── Notebook mention patterns ──────────────────────────────────────────────────

NOTEBOOK_PATTERNS = [
    r"jupyter\s+lab",
    r"jupyter\s+notebook",
    r"jupyter",
    r"\.ipynb",
    r"ipynb",
]
NOTEBOOK_RE = re.compile(
    "|".join(NOTEBOOK_PATTERNS),
    re.IGNORECASE,
)

# ── Hosting detection (mirrors collect_ads.py) ─────────────────────────────────

def detect_host_type(url):
    u = url.lower()
    if "github.com"  in u or "github.io"  in u: return "github"
    if "zenodo.org"  in u:                       return "zenodo"
    if "gitlab.com"  in u:                       return "gitlab"
    if "bitbucket.org" in u:                     return "bitbucket"
    if "figshare.com"  in u:                     return "figshare"
    if "mybinder.org"  in u or "binder." in u:   return "binder"
    if "colab.research.google.com" in u:         return "colab"
    if "osf.io"        in u:                     return "osf"
    if "dataverse"     in u:                     return "dataverse"
    if "huggingface.co" in u:                    return "huggingface"
    return "personal_site"


# ── LaTeX section detection ────────────────────────────────────────────────────

# Matches \section, \subsection, \subsubsection (starred or not)
SECTION_RE = re.compile(
    r"\\(?:sub)*section\*?\s*\{([^}]{1,120})\}",
    re.IGNORECASE,
)

# Heuristic labels for special environments detected by keyword
SPECIAL_SECTION_PATTERNS = [
    (re.compile(r"\\begin\{abstract\}",      re.IGNORECASE), "abstract"),
    (re.compile(r"\\begin\{acknowledgment",  re.IGNORECASE), "acknowledgments"),
    (re.compile(r"data.avail",               re.IGNORECASE), "data_availability"),
    (re.compile(r"\\begin\{thebibliography\}|\\bibliography\{", re.IGNORECASE), "references"),
    (re.compile(r"\\footnote\s*\{",          re.IGNORECASE), "footnote_env"),
]


def build_section_map(tex_text):
    """
    Return a sorted list of (char_position, section_label) pairs covering
    the whole document so we can binary-search for the nearest section
    heading above any match position.
    """
    entries = [(0, "preamble")]

    for pat, label in SPECIAL_SECTION_PATTERNS:
        for m in pat.finditer(tex_text):
            entries.append((m.start(), label))

    for m in SECTION_RE.finditer(tex_text):
        label = m.group(1).strip()
        # Strip nested LaTeX commands for readability, e.g. \texttt{jupyter}
        label = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", label)
        label = re.sub(r"\\[a-zA-Z]+",            "",      label)
        label = label.strip()
        entries.append((m.start(), label or "unknown"))

    entries.sort(key=lambda x: x[0])
    return entries


def section_at(section_map, pos):
    """Return the section label that was active at character position pos."""
    label = "body"
    for start, sec_label in section_map:
        if start <= pos:
            label = sec_label
        else:
            break
    return label


# ── Link-form detection ────────────────────────────────────────────────────────

# URL inside \url{} or \href{}{} or raw http(s)
URL_IN_BRACES_RE = re.compile(
    r"\\(?:url|href)\s*\{([^}]+)\}|"      # \url{...} or \href{...}{...}
    r"(https?://[^\s\]\)\}\"\'<>]{4,})",   # raw URL
    re.IGNORECASE,
)

DOI_RE = re.compile(
    r"\\doi\s*\{[^}]+\}|"
    r"doi\s*:\s*10\.[^\s\]\)\}\"\'<>]+",
    re.IGNORECASE,
)

FOOTNOTE_RE = re.compile(r"\\footnote\s*\{", re.IGNORECASE)


def extract_link_context(tex_text, match_start, match_end, window=300):
    """
    Within a ±window char slice around the match, detect the link form and
    extract any URL.

    Returns (link_form, url) where link_form is one of:
        url | doi | footnote | plain_text
    """
    lo  = max(0, match_start - window)
    hi  = min(len(tex_text), match_end + window)
    snip = tex_text[lo:hi]

    # Check for URL first (most specific)
    url_match = URL_IN_BRACES_RE.search(snip)
    if url_match:
        url = url_match.group(1) or url_match.group(2) or ""
        url = url.strip().rstrip(".,;)")
        return "url", url if url else None

    # DOI
    if DOI_RE.search(snip):
        doi_m = DOI_RE.search(snip)
        return "doi", doi_m.group(0) if doi_m else None

    # Footnote (mention is inside or adjacent to a footnote)
    if FOOTNOTE_RE.search(snip):
        return "footnote", None

    return "plain_text", None


# ── Context window ─────────────────────────────────────────────────────────────

def extract_context(tex_text, match_start, match_end, window=200):
    """Return ±window chars around the match, with whitespace collapsed."""
    lo  = max(0, match_start - window)
    hi  = min(len(tex_text), match_end + window)
    ctx = tex_text[lo:hi]
    ctx = re.sub(r"\s+", " ", ctx).strip()
    return ctx


# ── arXiv fetch ────────────────────────────────────────────────────────────────

def fetch_arxiv_source(arxiv_id):
    """
    Fetch the arXiv e-print tarball for arxiv_id.
    Returns a list of (filename, text_content) pairs for all .tex files found,
    or an empty list on failure.
    """
    url = ARXIV_EPRINT_URL.format(arxiv_id=arxiv_id)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT,
                            headers={"User-Agent": "ReproducibilityAstro/1.0 (research pipeline)"})
        if resp.status_code == 404:
            print(f"  [arXiv] 404 — {arxiv_id}")
            return []
        if resp.status_code == 429:
            print(f"  [arXiv] Rate limited on {arxiv_id} — waiting 60s...")
            time.sleep(60)
            return fetch_arxiv_source(arxiv_id)
        if resp.status_code != 200:
            print(f"  [arXiv] HTTP {resp.status_code} for {arxiv_id}")
            return []
    except requests.RequestException as e:
        print(f"  [arXiv] Request failed for {arxiv_id}: {e}")
        return []

    content = resp.content
    tex_files = []

    # Try tar.gz (most common)
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".tex"):
                    try:
                        f = tar.extractfile(member)
                        if f:
                            raw = f.read()
                            text = _decode(raw)
                            if text:
                                tex_files.append((member.name, text))
                    except Exception:
                        pass
        if tex_files:
            return tex_files
    except tarfile.TarError:
        pass

    # Try plain gzip (.tex.gz or single-file submission)
    try:
        text = _decode(gzip.decompress(content))
        if text and NOTEBOOK_RE.search(text):
            return [(f"{arxiv_id}.tex", text)]
    except Exception:
        pass

    # Try raw .tex (some very old submissions)
    try:
        text = _decode(content)
        if text and NOTEBOOK_RE.search(text):
            return [(f"{arxiv_id}.tex", text)]
    except Exception:
        pass

    print(f"  [arXiv] Could not parse source for {arxiv_id}")
    return []


def _decode(raw_bytes):
    """Try UTF-8 then latin-1 decoding."""
    for enc in ("utf-8", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            pass
    return None


# ── Mention extraction ─────────────────────────────────────────────────────────

def extract_mentions_from_tex(tex_text):
    """
    Find all notebook mentions in a single .tex file.
    Returns list of dicts with keys:
        mention_text, context, section, link_form, url, host
    """
    section_map = build_section_map(tex_text)
    mentions    = []

    for m in NOTEBOOK_RE.finditer(tex_text):
        mention_text = m.group(0)
        pos_start    = m.start()
        pos_end      = m.end()

        context            = extract_context(tex_text, pos_start, pos_end)
        section            = section_at(section_map, pos_start)
        link_form, url     = extract_link_context(tex_text, pos_start, pos_end)

        host = "none"
        if url:
            host = detect_host_type(url)

        mentions.append({
            "mention_text": mention_text,
            "context":      context,
            "section":      section,
            "link_form":    link_form,
            "url":          url,
            "host":         host,
        })

    return mentions


def deduplicate_mentions(mentions):
    """
    Remove near-duplicate mentions (same context string).
    Keeps the first occurrence.
    """
    seen    = set()
    results = []
    for m in mentions:
        key = m["context"][:120]
        if key not in seen:
            seen.add(key)
            results.append(m)
    return results


# ── Category update ────────────────────────────────────────────────────────────

def refined_category_from_mentions(mentions, existing_category):
    """
    If full-text extraction reveals a hosting platform not captured in the
    abstract-level classification, upgrade the category.

    Priority: jupyter_with_github_zenodo > jupyter_with_github >
              jupyter_with_zenodo > jupyter_with_personal > jupyter_only
    """
    hosts = {m["host"] for m in mentions if m["host"] not in ("none", "personal_site")}
    hosts_all = {m["host"] for m in mentions}

    has_github  = "github"  in hosts
    has_zenodo  = "zenodo"  in hosts
    has_personal = any(h in hosts_all for h in
                       ("gitlab","bitbucket","figshare","binder",
                        "colab","osf","dataverse","huggingface","personal_site"))

    # Build new category from full-text evidence
    if has_github and has_zenodo:
        new_cat = "jupyter_with_github_zenodo"
    elif has_github:
        new_cat = "jupyter_with_github"
    elif has_zenodo:
        new_cat = "jupyter_with_zenodo"
    elif has_personal:
        new_cat = "jupyter_with_personal"
    else:
        new_cat = existing_category  # no new information

    # Only upgrade, never downgrade
    priority = {
        "jupyter_only":               0,
        "jupyter_with_personal":      1,
        "jupyter_with_zenodo":        2,
        "jupyter_with_github":        3,
        "jupyter_with_github_zenodo": 4,
    }
    if priority.get(new_cat, 0) > priority.get(existing_category, 0):
        return new_cat
    return existing_category


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_unprocessed_articles(conn, limit=None):
    """
    Return articles that have an arXiv ID and no existing notebook_mentions rows.
    """
    cur = conn.cursor()
    sql = """
        SELECT a.id, a.pmc, a.notebook_category
        FROM article a
        WHERE a.pmc IS NOT NULL
          AND a.pmc != ''
          AND a.id NOT IN (
              SELECT DISTINCT article_id FROM notebook_mentions
          )
        ORDER BY a.id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    return cur.fetchall()


def insert_mentions(conn, article_id, mentions):
    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO notebook_mentions
               (article_id, mention_text, context, section, link_form, url, host)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (article_id,
             m["mention_text"],
             m["context"],
             m["section"],
             m["link_form"],
             m["url"],
             m["host"])
            for m in mentions
        ]
    )
    conn.commit()


def update_article_category(conn, article_id, new_category):
    cur = conn.cursor()
    cur.execute(
        "UPDATE article SET notebook_category = ? WHERE id = ?",
        (new_category, article_id)
    )
    conn.commit()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract notebook mentions from arXiv LaTeX source.")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most N articles (useful for testing). Default: all."
    )
    args = parser.parse_args()

    if not DB_FILE.exists():
        print(f"[ERROR] Database not found at {DB_FILE}")
        print("  Run collect.sh first.")
        return

    conn = sqlite3.connect(DB_FILE)
    articles = get_unprocessed_articles(conn, limit=args.limit)

    total = len(articles)
    if total == 0:
        print("[MENTIONS] No unprocessed articles found.")
        print("  Either collect.sh has not been run, or all articles")
        print("  have already been processed.")
        conn.close()
        return

    print(f"[MENTIONS] {total} articles to process.\n")

    processed     = 0
    skipped_no_source = 0
    total_mentions    = 0
    category_updates  = 0

    for idx, (article_id, arxiv_id, existing_category) in enumerate(articles, 1):
        print(f"[{idx}/{total}] arXiv:{arxiv_id}  (current category: {existing_category})")

        tex_files = fetch_arxiv_source(arxiv_id)

        if not tex_files:
            skipped_no_source += 1
            # Insert a sentinel row so we don't retry this article on next run
            insert_mentions(conn, article_id, [{
                "mention_text": "__no_source__",
                "context":      None,
                "section":      None,
                "link_form":    None,
                "url":          None,
                "host":         None,
            }])
            time.sleep(REQUEST_DELAY_SEC)
            continue

        # Collect mentions across all .tex files
        all_mentions = []
        for filename, tex_text in tex_files:
            file_mentions = extract_mentions_from_tex(tex_text)
            print(f"  [{filename}] {len(file_mentions)} mention(s)")
            all_mentions.extend(file_mentions)

        all_mentions = deduplicate_mentions(all_mentions)

        # Filter out sentinel-only result
        real_mentions = [m for m in all_mentions if m["mention_text"] != "__no_source__"]

        if real_mentions:
            insert_mentions(conn, article_id, real_mentions)
            total_mentions += len(real_mentions)

            # Refine category from full-text evidence
            new_category = refined_category_from_mentions(real_mentions, existing_category)
            if new_category != existing_category:
                update_article_category(conn, article_id, new_category)
                print(f"  [CATEGORY] {existing_category} → {new_category}")
                category_updates += 1
        else:
            # No mentions found in source (title/abstract match but not body)
            insert_mentions(conn, article_id, [{
                "mention_text": "__no_mentions__",
                "context":      None,
                "section":      None,
                "link_form":    None,
                "url":          None,
                "host":         None,
            }])

        processed += 1
        time.sleep(REQUEST_DELAY_SEC)

    conn.close()

    print(f"\n[DONE]")
    print(f"  Articles processed       : {processed}")
    print(f"  Skipped (no arXiv source): {skipped_no_source}")
    print(f"  Total mentions inserted  : {total_mentions}")
    print(f"  Category upgrades        : {category_updates}")


if __name__ == "__main__":
    main()
