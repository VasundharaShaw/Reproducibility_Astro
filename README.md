# Reproducibility_Astro

**Automated Repository-Level Reproducibility Assessment for Astrophysics Jupyter Notebooks**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: NFDI JupyterHub](https://img.shields.io/badge/platform-NFDI%20JupyterHub-orange.svg)](https://hub.nfdi-jupyter.de)

---

## Overview

This pipeline is adapted from the [CPRMC biomedical reproducibility pipeline](https://github.com/VasundharaShaw/CPRMC_version_Vasu) and targets astrophysics publications. It automatically collects astrophysics papers from NASA ADS that mention GitHub and Jupyter notebooks, verifies that the linked repos contain notebooks via the GitHub API, then clones, executes, and measures the reproducibility of those notebooks in isolated Python environments.

It is designed to run on the **[NFDI JupyterHub](https://hub.nfdi-jupyter.de)** — no local Docker installation needed.

Results are stored in a SQLite database for downstream analysis.

### What it does

1. **Collects** astrophysics papers from NASA ADS (last 15 years) mentioning GitHub and Jupyter in title, abstract, or body text
2. **Verifies** each linked GitHub repo contains `.ipynb` files via the GitHub API before storing
3. **Clones** confirmed repositories
4. **Detects** the required Python version from each repo's metadata
5. **Creates** an isolated pyenv + venv environment per repository
6. **Executes** each notebook via `nbconvert`
7. **Compares** original vs. re-executed outputs
8. **Stores** cell-level reproducibility scores in a SQLite database

---

## Running on NFDI JupyterHub (recommended)

1. Go to [hub.nfdi-jupyter.de](https://hub.nfdi-jupyter.de/hub/home)
2. Click **Start Server** and choose **Repo2docker (Binder)**
3. Fill in the form:
   - **Repository URL**: `https://github.com/VasundharaShaw/Reproducibility_Astro`
   - **Git ref**: `main`
   - **Flavor**: `4GB RAM, 1 vCPU` (minimum recommended)
4. Click **Start** — the environment will build automatically
5. Once JupyterLab opens, launch a terminal and run:

```bash
cd /home/jovyan
export ADS_API_TOKEN=your_ads_token_here
export GITHUB_API_TOKEN=your_github_token_here
bash collect.sh
bash run.sh
```

---

## Repository Structure

```
Reproducibility_Astro/
├── collect.sh               # Step 1 — collect papers and repos from NASA ADS
├── run.sh                   # Step 2 — clone, execute, and compare notebooks
├── binder/                  # repo2docker configuration
├── config/
│   └── config.sh            # Pipeline configuration (paths, settings)
├── data/
│   └── db.sqlite            # Input database — articles, journals, authors, repos with notebooks
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
│   ├── collect_ads.py       # NASA ADS collection + GitHub API notebook check
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

| Token | Where to get it |
|---|---|
| `ADS_API_TOKEN` | [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu) → Account → Settings → API Token |
| `GITHUB_API_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens |

```bash
export ADS_API_TOKEN=your_ads_token_here
export GITHUB_API_TOKEN=your_github_token_here
```

### Dependencies
- Python 3
- SQLite3
- Git
- pyenv

---

## Usage

### Step 1 — Collect papers and repos

```bash
bash collect.sh
```

Queries NASA ADS for astrophysics papers (last 15 years) that mention GitHub and Jupyter in their title, abstract, or body text. For each GitHub repo found, queries the GitHub API to confirm `.ipynb` files exist before inserting into `data/db.sqlite`.

### Step 2 — Run the pipeline

```bash
bash run.sh
```

You will be prompted to choose a mode:

#### Mode 1 — Single repository

Enter a GitHub repository URL directly. You will be asked for:
- **GitHub repo URL** — e.g. `https://github.com/example/repo`
- **Notebook paths** — semicolon-separated paths to `.ipynb` files within the repo
- **Setup paths** *(optional)* — paths to `setup.py` files
- **Requirements paths** *(optional)* — paths to `requirements.txt` files

#### Mode 2 — Batch mode

Processes repos from `data/db.sqlite` automatically. Results are written to `output/db/db.sqlite` — the input database is never modified.

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
export TARGET_COUNT=20    # Override batch size (default: 10)
bash run.sh
```

---

## Database Architecture

The pipeline uses two separate SQLite databases:

| Database | Path | Purpose |
|---|---|---|
| Input DB | `data/db.sqlite` | Populated by `collect.sh` — articles, journals, authors, repos confirmed to have notebooks. **Never modified by `run.sh`.** |
| Output DB | `output/db/db.sqlite` | Created by `run.sh` — stores all execution results. |

### Output database tables

| Table | Description |
|---|---|
| `repositories` | Repository metadata (URL, notebook count, requirements) |
| `repository_runs` | Per-run status, timestamps, duration |
| `notebook_executions` | Per-notebook execution results and errors |
| `notebook_reproducibility_metrics` | Cell-level reproducibility scores |

### Example queries

```sql
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

-- Success rate by whether repo had a requirements.txt
SELECT
    CASE WHEN requirements IS NOT NULL THEN 'With requirements.txt'
         ELSE 'Without requirements.txt' END AS req_status,
    COUNT(*) AS total,
    SUM(CASE WHEN run_status = 'SUCCESS' THEN 1 ELSE 0 END) AS successful
FROM repositories r
JOIN repository_runs rr ON r.id = rr.repository_id
GROUP BY req_status;
```

To explore results interactively, open `analysis/analyse_reporesults.ipynb` in JupyterLab.

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
