# Reproducibility_Astro

**Automated Repository-Level Reproducibility Assessment for Astrophysics Jupyter Notebooks**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: NFDI JupyterHub](https://img.shields.io/badge/platform-NFDI%20JupyterHub-orange.svg)](https://hub.nfdi-jupyter.de)

---

## Overview

This pipeline is adapted from the [CPRMC biomedical reproducibility pipeline](https://github.com/VasundharaShaw/CPRMC_version_Vasu) and targets astrophysics publications. It collects astrophysics papers from NASA ADS that mention Jupyter notebooks (regardless of hosting platform), extracts full-text mention context from arXiv LaTeX source, then clones, scores, executes, and measures the reproducibility of those notebooks in isolated Python environments.

It is designed to run on the **[NFDI JupyterHub](https://hub.nfdi-jupyter.de)** — no local Docker installation needed.

All results are stored in a single SQLite database at `output/db/db.sqlite`.

### Research Questions

1. **How are Jupyter notebooks referenced in astronomy publications?** — section, link form, and mention context extracted from full LaTeX source
2. **How stable are the referenced Jupyter notebooks?** — execution success rates and RRS reproducibility scores
3. **Where are referenced Jupyter notebooks located or stored?** — hosting platform classification (GitHub, Zenodo, GitLab, personal sites, etc.)
4. **How do Jupyter notebooks receive links and citations?** — URL vs DOI vs footnote vs plain-text citation mechanics

### What it does

1. **Collects** astrophysics papers from NASA ADS (last 2 months) mentioning Jupyter notebooks in title, abstract, or body text — across any hosting platform
2. **Classifies** each paper by notebook category based on co-occurring hosting signals
3. **Fetches** arXiv LaTeX source tarballs and extracts every notebook mention with full context, section, link form, and host
4. **Clones** GitHub-hosted repositories
5. **Scores** each repository using Sheeba Samuel's [ReproScore (RRS)](https://github.com/myVSR/reproscore) framework (5 categories, 0–100 scale)
6. **Detects** the required Python version from each repo's metadata
7. **Creates** an isolated pyenv + venv environment per repository
8. **Executes** each notebook via `nbconvert`
9. **Compares** original vs. re-executed outputs
10. **Stores** all results in `output/db/db.sqlite`

---

## RRS Scoring — Repository Readiness

Each cloned repository is scored using the vendored [ReproScore](https://github.com/myVSR/reproscore) framework (see `pipeline/reproscore/`). Scores are computed across five categories and written to the `repo_targets` table.

| Column | Category | Weight | Description |
|---|---|---|---|
| `score_E` | Environment | 30% | Requirements files, Dockerfile, environment spec |
| `score_A` | Data Access | 25% | Zenodo/DOI links, data directories, download scripts |
| `score_D` | Documentation | 20% | README quality, markdown cells in notebooks |
| `score_C` | Code Quality | 15% | Code organisation, error handling, cell structure |
| `score_S` | Repro. Signals | 10% | CI config, random seeds, test suite, Binder badge |
| `rrs` | **Total RRS** | — | Weighted composite score, 0–100 |

Scoring runs automatically during `run.sh` after notebook discovery and before environment setup.

---

## Running on NFDI JupyterHub (recommended)

1. Go to [hub.nfdi-jupyter.de](https://hub.nfdi-jupyter.de/hub/home)
2. Click **Start Server** and choose **Repo2docker (Binder)**
3. Fill in the form:
   - **Repository URL**: `https://github.com/VasundharaShaw/Reproducibility_Astro`
   - **Git ref**: `main`
   - **Flavor**: `8GB RAM, 2 vCPU` (recommended)
4. Click **Start** — repo2docker builds the environment from `binder/Dockerfile` automatically
5. Once JupyterLab opens, launch a terminal and run:

```bash
export ADS_API_TOKEN=your_ads_token_here
bash collect.sh
bash mentions.sh --limit 50    # test with 50 articles; remove --limit for full run
TARGET_COUNT=5 bash run.sh     # process 5 repos at a time to avoid memory limits
```

> **Note:** Git identity and environment variables reset between JupyterHub sessions. Re-export tokens and re-run `git config --global` after each login.

---

## Repository Structure

```
Reproducibility_Astro/
├── collect.sh               # Step 1 — collect papers from NASA ADS
├── mentions.sh              # Step 2 — extract notebook mentions from arXiv LaTeX source
├── run.sh                   # Step 3 — clone, score, execute, and compare notebooks
├── binder/                  # repo2docker environment definition
│   ├── Dockerfile           # Full environment spec — Python, Jupyter, pyenv, nbdime
│   ├── apt.txt              # Additional system packages for pyenv build dependencies
│   └── postBuild            # Post-build script — configures pyenv PATH
├── config/
│   └── config.sh            # Pipeline configuration (paths, DB location, settings)
├── output/                  # All pipeline outputs (created at runtime)
│   ├── cloned_repos/        # Cloned repositories
│   ├── db/
│   │   └── db.sqlite        # Single DB — all collection and execution results
│   ├── logs/                # Per-repo execution logs
│   └── comparisons/         # JSON comparison reports
├── src/                     # Shell library functions
│   ├── pyenv.sh             # Python version detection + venv isolation
│   ├── repo.sh              # Repository cloning, notebook discovery, scoring, processing
│   ├── requirements.sh      # Dependency extraction
│   ├── notebooks.sh         # Notebook execution and comparison logic
│   ├── db.sh                # Database operations + schema
│   ├── checks.sh            # Pre-flight validation
│   └── logging.sh           # Logging utilities
├── pipeline/
│   ├── collect_ads.py       # NASA ADS collection + article categorisation
│   ├── extract_mentions.py  # arXiv LaTeX full-text mention extractor
│   ├── score.py             # RRS scoring — calls vendored reproscore
│   ├── main.sh              # Main pipeline orchestrator
│   └── reproscore/          # Vendored ReproScore package (Sheeba Samuel, TU Chemnitz)
│       ├── scoring/
│       │   ├── rrs.py       # RRSScorer — main scoring class
│       │   └── rubric.py    # Scoring rubric definitions
│       └── utils/
│           └── notebook_paths.py
├── config/
│   └── default_rubric.yaml  # RRS rubric configuration
├── analysis/
│   ├── astro_reproducibility_analysis.ipynb  # Main analysis notebook (4 RQs + ablation)
│   ├── compare_notebook.py  # Output comparison script
│   └── nbprocess/           # Notebook processing utilities
├── input/                   # Input repo lists for batch mode
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
pip install requests nbformat nbdime nbconvert pandas matplotlib seaborn scipy
```

You also need Python 3.10+, SQLite3, Git, and pyenv installed on your system.

---

## Usage

### Step 1 — Collect papers

```bash
bash collect.sh
```

Queries NASA ADS for astrophysics papers (last 2 months) that mention Jupyter notebooks in their title, abstract, or body text. Each paper is classified into a notebook category and written to `output/db/db.sqlite`.

### Step 2 — Extract notebook mentions

```bash
bash mentions.sh
# or with a limit for testing:
bash mentions.sh --limit 10
```

For each article with an arXiv ID, fetches the LaTeX source tarball and extracts every notebook mention into the `notebook_mentions` table. Idempotent — already-processed articles are skipped. arXiv requests are rate-limited to 1 per 3 seconds.

### Step 3 — Create pipeline tables

```bash
bash -c 'source config/config.sh; source src/logging.sh; source src/db.sh; ensure_pipeline_tables'
```

Only needed on a fresh session before the first `run.sh` call.

### Step 4 — Run the pipeline

```bash
TARGET_COUNT=2 bash run.sh
```

Processes GitHub-hosted repositories. For each repo the pipeline clones it, scores it with RRS, sets up an isolated Python environment, executes all notebooks, and compares outputs. Choose batch mode (option 2) to process repos from the database automatically.

### Step 5 — Analyse results

Open `analysis/astro_reproducibility_analysis.ipynb` in JupyterLab and run all cells. The notebook covers all four research questions plus RRS ablation analysis (category means by failure mode, rank stability, LOCO, single-category AUC baselines).

---

## Database Schema

All data is stored in a single database at `output/db/db.sqlite`.

### Collection tables (populated by `collect.sh` and `mentions.sh`)

| Table | Description |
|---|---|
| `journal` | One row per publication venue |
| `article` | One row per paper — includes `notebook_category`, `doi`, `subject` |
| `author` | One row per author |
| `repositories` | One row per extracted repo/URL — includes `host_type` |
| `notebook_mentions` | One row per in-text notebook mention with context, section, link form, host |

### Execution tables (populated by `run.sh`)

| Table | Description |
|---|---|
| `repo_targets` | One row per processed repo — includes RRS columns (`rrs`, `score_E`, `score_A`, `score_D`, `score_C`, `score_S`) and `paper_doi` |
| `notebooks` | Individual notebook records per repository |
| `repository_runs` | Per-run status, timestamps, duration |
| `notebook_executions` | Per-notebook execution results and errors |
| `notebook_reproducibility_metrics` | Cell-level reproducibility scores |

---

## Notebook Categories

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
