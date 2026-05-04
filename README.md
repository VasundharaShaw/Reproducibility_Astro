# Reproducibility_Astro

**Automated Repository-Level Reproducibility Assessment for Astrophysics Jupyter Notebooks**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: NFDI JupyterHub](https://img.shields.io/badge/platform-NFDI%20JupyterHub-orange.svg)](https://hub.nfdi-jupyter.de)

---

## Overview

This pipeline is adapted from the [CPRMC biomedical reproducibility pipeline](https://github.com/VasundharaShaw/CPRMC_version_Vasu) and targets astrophysics publications. It collects astrophysics papers from NASA ADS that mention Jupyter notebooks (regardless of hosting platform), extracts full-text mention context from arXiv LaTeX source, then clones, executes, and measures the reproducibility of those notebooks in isolated Python environments.

It is designed to run on the **[NFDI JupyterHub](https://hub.nfdi-jupyter.de)** — no local Docker installation needed.

Results are stored in two SQLite databases: one for collected article metadata and mention context, one for pipeline execution results.

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
5. **Detects** the required Python version from each repo's metadata
6. **Creates** an isolated pyenv + venv environment per repository
7. **Executes** each notebook via `nbconvert`
8. **Compares** original vs. re-executed outputs
9. **Stores** cell-level reproducibility scores in a SQLite database

---

## How the Environment Works (repo2docker + Dockerfile)

This repository uses **[repo2docker](https://repo2docker.readthedocs.io)** to define its compute environment. When you launch this repo on NFDI JupyterHub, repo2docker reads `binder/Dockerfile` and automatically builds a container image from it — no manual setup required on your part.

### What repo2docker does

repo2docker is a tool that converts a repository into a reproducible computational environment. It looks for configuration files in the `binder/` folder (such as a `Dockerfile`, `requirements.txt`, or `environment.yml`) and uses them to build a Docker image. That image becomes the JupyterHub server you work in.

When you paste the GitHub URL into NFDI JupyterHub and click Start, repo2docker:
1. Clones this repository
2. Reads `binder/Dockerfile`
3. Builds a container image with all dependencies pre-installed
4. Launches JupyterLab inside that container

On first launch this takes a few minutes. Subsequent launches reuse the cached image and are much faster.

### What `binder/Dockerfile` installs

The `binder/Dockerfile` defines the complete runtime environment:

- **Base**: Ubuntu 22.04
- **System packages**: build tools required by pyenv (`make`, `build-essential`, `libssl-dev`, `zlib1g-dev`, etc.)
- **Python 3.10**: installed system-wide via apt
- **Jupyter stack**: `notebook`, `jupyterlab`, `nbconvert`, `nbformat`, `nbdime` — available to all pipeline scripts without manual installation
- **Pipeline dependencies**: `requests` — used by `collect_ads.py` and `extract_mentions.py`
- **pyenv**: installed as the `jovyan` user so the pipeline can create per-repository isolated Python environments at run time

Because all of this is baked into the image, you never need to run `pip install` manually after launching on NFDI JupyterHub.

### Why two Python environments?

The pipeline intentionally uses two separate Python contexts:

| Context | What it is | Used for |
|---|---|---|
| System Python (Dockerfile) | Python 3.10, installed at image build time | Running `collect.sh`, `mentions.sh`, `compare_notebook.py` |
| Per-repo venv (pyenv) | Fresh venv created per repository at pipeline run time | Executing each cloned repo's notebooks in isolation |

This separation ensures a repo's dependencies never pollute the pipeline environment, and each repo gets a clean environment that matches its own `requirements.txt`.

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
export TARGET_COUNT=5          # process 5 repos at a time to avoid memory limits
bash run.sh
```

---

## Repository Structure

```
Reproducibility_Astro/
├── collect.sh               # Step 1 — collect papers from NASA ADS → data/db.sqlite
├── mentions.sh              # Step 2 — extract notebook mentions from arXiv LaTeX source
├── run.sh                   # Step 3 — clone, execute, and compare notebooks
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
│   ├── repo.sh              # Repository cloning, notebook discovery, and processing
│   ├── requirements.sh      # Dependency extraction
│   ├── notebooks.sh         # Notebook execution and comparison logic
│   ├── db.sh                # Database operations + schema
│   ├── checks.sh            # Pre-flight validation
│   └── logging.sh           # Logging utilities
├── pipeline/
│   ├── collect_ads.py       # NASA ADS collection + article categorisation
│   ├── extract_mentions.py  # arXiv LaTeX full-text mention extractor
│   └── main.sh              # Main pipeline orchestrator
├── analysis/
│   ├── compare_notebook.py  # Output comparison script
│   ├── analyse_reporesults.ipynb  # Explore results interactively
│   └── nbprocess/           # Notebook processing utilities
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

All dependencies are pre-installed by `binder/Dockerfile` when running on NFDI JupyterHub. If running locally outside of JupyterHub:

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

Queries NASA ADS for astrophysics papers (last 5 years) that mention Jupyter notebooks in their title, abstract, or body text. No GitHub filter is applied at collection time — papers are collected regardless of where their notebooks are hosted. Each paper is classified into one of five notebook categories (see below) and written to `data/db.sqlite`.

### Step 2 — Extract notebook mentions

```bash
bash mentions.sh
# or with a limit for testing:
bash mentions.sh --limit 10
```

For each article in `data/db.sqlite` that has an arXiv ID, fetches the LaTeX source tarball from arXiv and extracts every notebook mention into the `notebook_mentions` table. Captured per mention:

- **mention_text** — the matched keyword or phrase
- **context** — ±200 characters of surrounding text
- **section** — nearest LaTeX section heading (e.g. `Introduction`, `data_availability`, `abstract`)
- **link_form** — `url`, `doi`, `footnote`, or `plain_text`
- **url** — the adjacent URL if present
- **host** — detected hosting platform (`github`, `zenodo`, `gitlab`, `personal_site`, etc.)

This step is idempotent — articles already processed are skipped on re-runs. arXiv requests are rate-limited to 1 per 3 seconds.

### Step 3 — Run the pipeline

```bash
bash run.sh
# recommended on JupyterHub to avoid memory limits:
export TARGET_COUNT=5
bash run.sh
```

Processes GitHub-hosted repositories only (Zenodo and personal site entries are reserved for a future download stage). You will be prompted to choose a mode:

#### Mode 1 — Single repository

Enter a GitHub repository URL directly. You will be asked for:
- **GitHub repo URL** — e.g. `https://github.com/example/repo`
- **Notebook paths** — semicolon-separated paths to `.ipynb` files within the repo
- **Setup paths** *(optional)* — paths to `setup.py` files
- **Requirements paths** *(optional)* — paths to `requirements.txt` files

#### Mode 2 — Batch mode

Processes GitHub repos from `data/db.sqlite` automatically. Results are written to `output/db/db.sqlite` — the input database is never modified.

---

## Notebook Categories

Each article is classified at collection time based on what hosting signals co-occur with Jupyter/ipynb indicators. Classification is refined when full-text arXiv source is available.

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
| hep-ex | High energy physics - experiment |
| hep-ph | High energy physics - phenomenology |
| hep-th | High energy physics - theory |
| hep-lat | High energy physics - lattice |

---

## How Environment Isolation Works

Each repository gets its own isolated Python environment via **pyenv + venv**:

1. Detects the required Python version by checking (in order):
   - `binder/runtime.txt`
   - `runtime.txt`
   - `.python-version`
   - `setup.py` / `setup.cfg` `python_requires` field
   - Falls back to Python 3.10
2. Installs that Python version via pyenv if not already present
3. Creates a fresh virtual environment under `~/.repo_venvs/<repo-name>/`
4. Installs the repo's dependencies into the venv
5. Executes all notebooks inside the venv
6. Cleans up the venv after execution

---

## Configuration

Edit `config/config.sh` or set environment variables before running:

```bash
export TARGET_COUNT=5     # Repos per batch (keep low on 4-8GB instances)
bash run.sh
```

---

## Database Architecture

The pipeline uses two separate SQLite databases:

| Database | Path | Purpose |
|---|---|---|
| Input DB | `data/db.sqlite` | Populated by `collect.sh` and `mentions.sh`. Stores articles, journals, authors, repositories, and notebook mentions. **Never modified by `run.sh`.** |
| Output DB | `output/db/db.sqlite` | Created by `run.sh`. Stores all execution results. |

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
| `repositories` | Repository metadata (URL, notebook count, requirements, `host_type`) |
| `notebooks` | Individual notebook records per repository |
| `repository_runs` | Per-run status, timestamps, duration |
| `notebook_executions` | Per-notebook execution results and errors |
| `notebook_reproducibility_metrics` | Cell-level reproducibility scores |

### Example queries

```sql
-- How are notebooks referenced? (section breakdown)
SELECT section, COUNT(*) AS mentions
FROM notebook_mentions
WHERE mention_text NOT LIKE '__%__'
GROUP BY section
ORDER BY mentions DESC;

-- Link form distribution
SELECT link_form, COUNT(*) AS count
FROM notebook_mentions
WHERE mention_text NOT LIKE '__%__'
GROUP BY link_form
ORDER BY count DESC;

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

-- Reproducibility score distribution
SELECT
    CASE
        WHEN reproducibility_score = 1.0 THEN 'Perfect (1.0)'
        WHEN reproducibility_score >= 0.75 THEN 'High (0.75-1.0)'
        WHEN reproducibility_score >= 0.5  THEN 'Medium (0.5-0.75)'
        ELSE 'Low (<0.5)'
    END AS score_band,
    COUNT(*) AS notebooks
FROM notebook_reproducibility_metrics
GROUP BY score_band
ORDER BY notebooks DESC;
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
- **Email**: sheeba.samuel@informatik.tu-chemnitz.de
- **Research Group**: [Distributed and Self-organizing Systems, TU Chemnitz](https://vsr.informatik.tu-chemnitz.de/)
