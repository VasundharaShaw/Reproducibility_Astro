# Reproducibility_Astro

**Automated Repository-Level Reproducibility Assessment for Astrophysics Jupyter Notebooks**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: NFDI JupyterHub](https://img.shields.io/badge/platform-NFDI%20JupyterHub-orange.svg)](https://hub.nfdi-jupyter.de)

---

## Overview

This pipeline is adapted from the [CPRMC biomedical reproducibility pipeline](https://github.com/VasundharaShaw/CPRMC_version_Vasu) and targets astrophysics publications. It collects astrophysics papers from NASA ADS that mention Jupyter notebooks (regardless of hosting platform), extracts full-text mention context from arXiv LaTeX source, then clones, scores, executes, and measures the reproducibility of those notebooks in isolated Python environments.

It is designed to run on the **[NFDI JupyterHub](https://hub.nfdi-jupyter.de)** — no local Docker installation needed.

Results are stored in two SQLite databases: one for collected article metadata and mention context, one for pipeline execution results including ReproScore readiness scores.

### Research Questions

This pipeline is designed to answer four research questions about Jupyter notebooks in astrophysics publications:

1. **How are Jupyter notebooks referenced in astronomy publications?** — section, link form, and mention context extracted from full LaTeX source
2. **How stable are the referenced Jupyter notebooks?** — link health and repo availability over time *(future stage)*
3. **Where are referenced Jupyter notebooks located or stored?** — hosting platform classification (GitHub, Zenodo, GitLab, personal sites, etc.)
4. **How do Jupyter notebooks receive links and citations?** — URL vs DOI vs footnote vs plain-text citation mechanics

### What it does

1. **Collects** astrophysics papers from NASA ADS (last 5 years) mentioning Jupyter notebooks in title, abstract, or body text — across any hosting platform
2. **Classifies** each paper by notebook category based on co-occurring hosting signals
3. **Fetches** arXiv LaTeX source tarballs and extracts every notebook mention with full context, section, link form, and host
4. **Clones** GitHub-hosted repositories
5. **Scores** each repository using ReproScore (5 categories, 0–25 scale)
6. **Detects** the required Python version from each repo's metadata
7. **Creates** an isolated pyenv + venv environment per repository
8. **Executes** each notebook via `nbconvert`
9. **Compares** original vs. re-executed outputs
10. **Stores** cell-level reproducibility scores and ReproScore readiness scores in a SQLite database

---

## ReproScore — Repository Readiness Scoring

Each cloned repository is scored across five categories (0–5 points each, 25 total) before notebook execution begins. This measures *readiness* — static, file-based indicators of reproducibility — independent of whether the notebooks actually run.

| Category | Column | What earns points |
|---|---|---|
| **Environment specification** | `score_env` | `requirements.txt` (+1), `environment.yml` (+2), `Dockerfile` (+2), `setup.py`/`setup.cfg`/`pyproject.toml` (+1) |
| **Data accessibility** | `score_data` | Zenodo/DOI links in README or notebooks (+2), `/data` directory (+1), download scripts (+1), data-level README/LICENSE (+1) |
| **Documentation** | `score_docs` | README present (+1), README > 500 chars (+1), README > 2000 chars (+1), notebooks have markdown cells (+1), avg ≥ 3 markdown cells per notebook (+1) |
| **Code quality** | `score_code` | No excessive empty cells (+1), functions defined (+1), no bare `except:` clauses (+1), no error outputs in last cell (+1), organised layout (+1) |
| **Reproducibility signals** | `score_repro` | CI configured (+2), random seeds pinned (+1), test suite present (+1), Zenodo/Binder badge in README (+1) |

Scoring happens automatically during `run.sh` after notebook discovery and before environment setup. Scores are stored as columns on the `repositories` table in the output database.

---

## Running on NFDI JupyterHub (recommended)

1. Go to [hub.nfdi-jupyter.de](https://hub.nfdi-jupyter.de/hub/home)
2. Click **Start Server** and choose **Repo2docker (Binder)**
3. Fill in the form:
   - **Repository URL**: `https://github.com/VasundharaShaw/Reproducibility_Astro`
   - **Git ref**: `main`
   - **Flavor**: `8GB RAM, 2 vCPU` (recommended — the pipeline is memory-intensive)
4. Click **Start** — repo2docker builds the environment from `binder/Dockerfile` automatically
5. Once JupyterLab opens, launch a terminal and run:

```bash
cd /home/jovyan
export ADS_API_TOKEN=your_ads_token_here
bash collect.sh
bash mentions.sh --limit 50    # test with 50 articles; remove --limit for full run
export TARGET_COUNT=5           # process 5 repos at a time to avoid memory limits
bash run.sh
```

---

## Repository Structure

```
Reproducibility_Astro/
├── collect.sh               # Step 1 — collect papers from NASA ADS → data/db.sqlite
├── mentions.sh              # Step 2 — extract notebook mentions from arXiv LaTeX source
├── run.sh                   # Step 3 — clone, score, execute, and compare notebooks
├── binder/                  # repo2docker environment definition
│   ├── Dockerfile           # Full environment spec — Python, Jupyter, pyenv, nbdime
│   ├── apt.txt              # Additional system packages for pyenv build dependencies
│   └── postBuild            # Post-build script — configures pyenv PATH
├── config/
│   └── config.sh            # Pipeline configuration (paths, settings)
├── data/
│   └── db.sqlite            # Input DB — articles, journals, authors, repos, mentions
├── input/                   # Input repo lists for batch mode
├── output/                  # All pipeline outputs (created at runtime)
│   ├── cloned_repos/        # Cloned repositories
│   ├── db/                  # Execution results database (output/db/db.sqlite)
│   ├── logs/                # Per-repo execution logs
│   └── comparisons/         # JSON comparison reports
├── src/                     # Shell library functions
│   ├── pyenv.sh             # Python version detection + venv isolation
│   ├── repo.sh              # Repository cloning, notebook discovery, scoring, and processing
│   ├── requirements.sh      # Dependency extraction
│   ├── notebooks.sh         # Notebook execution and comparison logic
│   ├── db.sh                # Database operations + schema (incl. ReproScore columns)
│   ├── checks.sh            # Pre-flight validation
│   └── logging.sh           # Logging utilities
├── pipeline/
│   ├── collect_ads.py       # NASA ADS collection + article categorisation
│   ├── extract_mentions.py  # arXiv LaTeX full-text mention extractor
│   ├── score.py             # ReproScore — 5-category repository readiness scoring
│   └── main.sh              # Main pipeline orchestrator
├── analysis/
│   ├── compare_notebook.py  # Output comparison script
│   ├── analyse_reporesults.ipynb  # Explore results interactively
│   └── nbprocess/           # Notebook processing utilities (diff, summary, outputs)
└── tests/
    └── test_pipeline.sh     # Smoke test
```

---

## Setup

### Tokens required

| Token | Where to get it | Required for |
|---|---|---|
| `ADS_API_TOKEN` | [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu) → Account → Settings → API Token | `collect.sh` |
| `GITHUB_API_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens | `run.sh` (batch mode) |

```bash
export ADS_API_TOKEN=your_ads_token_here
export GITHUB_API_TOKEN=your_github_token_here   # only needed for run.sh
```

`mentions.sh` requires no API token — it fetches arXiv source directly.

### Dependencies

All dependencies are pre-installed by `binder/Dockerfile` when running on NFDI JupyterHub. If running locally:

```bash
pip install requests nbformat nbdime nbconvert
```

You also need Python 3.10+, SQLite3, Git, and pyenv installed on your system.

---

## Usage

### Step 1 — Collect papers

```bash
bash collect.sh
```

Queries NASA ADS for astrophysics papers (last 5 years) that mention Jupyter notebooks in their title, abstract, or body text. Each paper is classified into a notebook category and written to `data/db.sqlite`.

### Step 2 — Extract notebook mentions

```bash
bash mentions.sh
# or with a limit for testing:
bash mentions.sh --limit 10
```

For each article with an arXiv ID, fetches the LaTeX source tarball and extracts every notebook mention into the `notebook_mentions` table. This step is idempotent — articles already processed are skipped on re-runs. arXiv requests are rate-limited to 1 per 3 seconds.

### Step 3 — Run the pipeline

```bash
export TARGET_COUNT=5
bash run.sh
```

Processes GitHub-hosted repositories. For each repo, the pipeline clones it, scores it with ReproScore, sets up an isolated Python environment, executes all notebooks, and compares outputs. Choose batch mode (option 2) to process repos from the database automatically.

---

## Notebook Categories

Each article is classified at collection time based on hosting signals that co-occur with Jupyter/ipynb indicators.

| Category | Description |
|---|---|
| `jupyter_only` | Jupyter/ipynb indicators present; no recognised hosting platform mentioned |
| `jupyter_with_github` | Jupyter/ipynb + GitHub |
| `jupyter_with_zenodo` | Jupyter/ipynb + Zenodo |
| `jupyter_with_personal` | Jupyter/ipynb + personal/other website (GitLab, Binder, OSF, Figshare, etc.) |
| `jupyter_with_github_zenodo` | Jupyter/ipynb + both GitHub and Zenodo |

---

## Subject Categories Covered

| Category | Description |
|---|---|
| astro-ph.HE | High energy astrophysical phenomena |
| astro-ph.GA | Astrophysics of galaxies |
| astro-ph.CO | Cosmology and nongalactic astrophysics |
| astro-ph.EP | Earth and planetary astrophysics |
| astro-ph.IM | Instrumentation and methods for astrophysics |
| astro-ph.SR | Solar and stellar astrophysics |
| hep-ex | High energy physics — experiment |
| hep-ph | High energy physics — phenomenology |
| hep-th | High energy physics — theory |
| hep-lat | High energy physics — lattice |

---

## Database Architecture

The pipeline uses two separate SQLite databases:

| Database | Path | Purpose |
|---|---|---|
| Input DB | `data/db.sqlite` | Populated by `collect.sh` and `mentions.sh`. **Never modified by `run.sh`.** |
| Output DB | `output/db/db.sqlite` | Created by `run.sh`. Stores all execution results and ReproScore scores. |

### Input database tables (`data/db.sqlite`)

| Table | Populated by | Description |
|---|---|---|
| `journal` | `collect.sh` | One row per publication venue |
| `article` | `collect.sh` | One row per paper, includes `notebook_category` |
| `author` | `collect.sh` | One row per author |
| `repositories` | `collect.sh` | One row per extracted repo/URL, includes `host_type` |
| `notebook_mentions` | `mentions.sh` | One row per in-text notebook mention with full context |

### Output database tables (`output/db/db.sqlite`)

| Table | Description |
|---|---|
| `repositories` | Repository metadata, notebook count, requirements, `host_type`, and ReproScore columns (`score_env`, `score_data`, `score_docs`, `score_code`, `score_repro`, `score_total`) |
| `notebooks` | Individual notebook records per repository |
| `repository_runs` | Per-run status, timestamps, duration |
| `notebook_executions` | Per-notebook execution results and errors |
| `notebook_reproducibility_metrics` | Cell-level reproducibility scores |

### Example queries

```sql
-- ReproScore distribution across all scored repositories
SELECT score_total, COUNT(*) AS repos
FROM repositories
WHERE score_total IS NOT NULL
GROUP BY score_total
ORDER BY score_total DESC;

-- Average score by category
SELECT
    ROUND(AVG(score_env), 1) AS avg_env,
    ROUND(AVG(score_data), 1) AS avg_data,
    ROUND(AVG(score_docs), 1) AS avg_docs,
    ROUND(AVG(score_code), 1) AS avg_code,
    ROUND(AVG(score_repro), 1) AS avg_repro,
    ROUND(AVG(score_total), 1) AS avg_total
FROM repositories
WHERE score_total IS NOT NULL;

-- How are notebooks referenced? (section breakdown)
SELECT section, COUNT(*) AS mentions
FROM notebook_mentions
WHERE mention_text NOT LIKE '__%__'
GROUP BY section
ORDER BY mentions DESC;

-- Hosting platform distribution
SELECT host, COUNT(*) AS count
FROM notebook_mentions
WHERE url IS NOT NULL
GROUP BY host
ORDER BY count DESC;

-- Category breakdown
SELECT notebook_category, COUNT(*) AS papers
FROM article
GROUP BY notebook_category
ORDER BY papers DESC;

-- Repositories with highest average reproducibility score
SELECT r.repository, AVG(nrm.reproducibility_score) AS avg_score
FROM repositories r
JOIN notebook_reproducibility_metrics nrm ON r.id = nrm.repository_id
GROUP BY r.id
ORDER BY avg_score DESC
LIMIT 10;

-- Most common failure types
SELECT error_type, COUNT(*) AS count
FROM notebook_executions
WHERE execution_status NOT IN ('SUCCESS', 'SUCCESS_WITH_ERRORS')
GROUP BY error_type
ORDER BY count DESC;
```

---

## Related Publications

- Samuel, S., & Mietchen, D. (2024). Computational reproducibility of Jupyter notebooks from biomedical publications. *GigaScience*, 13, giad113. [DOI: 10.1093/gigascience/giad113](https://doi.org/10.1093/gigascience/giad113)
- Samuel, S., & Mietchen, D. (2024). FAIR Jupyter: A Knowledge Graph Approach to Semantic Sharing and Granular Exploration of a Computational Notebook Reproducibility Dataset. *TGDK*, 2(2), 4:1–4:24. [DOI: 10.4230/TGDK.2.2.4](https://doi.org/10.4230/TGDK.2.2.4)
- Samuel, S., & Mietchen, D. (2023). Dataset of a study of computational reproducibility of Jupyter notebooks from biomedical publications. *Zenodo*. [DOI: 10.5281/zenodo.8226725](https://doi.org/10.5281/zenodo.8226725)

---

## Acknowledgments

Supported by the **Jupyter4NFDI** project (DFG 567156310), **find.software** (DFG 567156310), **MaRDI** (DFG 460135501), **SeDOA** (DFG 556323977), and **HYP*MOL** (DFG 514664767).

---

## Contact

- **GitHub Issues**: [open an issue](https://github.com/VasundharaShaw/Reproducibility_Astro/issues)
- **Email**: vasundhara.shaw@fiz-karlsruhe.de, sheeba.samuel@informatik.tu-chemnitz.de
- **Research Group**: [zb-Math, FIZ-Karlsruhe](https://www.fiz-karlsruhe.de/de/bereiche/mathematische-informationsinfrastruktur), [Distributed and Self-organizing Systems, TU Chemnitz](https://vsr.informatik.tu-chemnitz.de/)
