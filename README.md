# Reproducibility_Astro

**Automated Repository-Level Reproducibility Assessment for Astrophysics Jupyter Notebooks**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: NFDI JupyterHub](https://img.shields.io/badge/platform-NFDI%20JupyterHub-orange.svg)](https://hub.nfdi-jupyter.de)

---

## Overview

This pipeline is adapted from the [CPRMC biomedical reproducibility pipeline](https://github.com/VasundharaShaw/CPRMC_version_Vasu) and targets astrophysics publications. It collects astrophysics papers from NASA ADS that mention Jupyter notebooks, extracts full-text mention context from arXiv LaTeX source, then clones, scores, executes, and measures the reproducibility of those notebooks in isolated Python environments.

It is designed to run on the **[NFDI JupyterHub](https://hub.nfdi-jupyter.de)** — no local Docker installation needed.

All results are stored in a single SQLite database at `output/db/db.sqlite`.

### Research Questions

1. **How are Jupyter notebooks referenced in astronomy publications?** — section, link form, and mention context extracted from full LaTeX source
2. **How stable are the referenced Jupyter notebooks?** — execution success rates and reproducibility scores
3. **Where are referenced Jupyter notebooks located or stored?** — hosting platform classification (GitHub, Zenodo, GitLab, personal sites, etc.)
4. **How do Jupyter notebooks receive links and citations?** — URL vs DOI vs footnote vs plain-text citation mechanics

### What it does

1. **Collects** astrophysics papers from NASA ADS (last 2 months) mentioning Jupyter notebooks
2. **Classifies** each paper by notebook category based on co-occurring hosting signals
3. **Fetches** arXiv LaTeX source tarballs and extracts every notebook mention with full context, section, link form, and host
4. **Clones** GitHub-hosted repositories
5. **Scores** each repository using Sheeba Samuel's [ReproScore (RRS)](https://github.com/myVSR/reproscore) framework (5 categories, 26 sub-metrics, 0–100 scale)
6. **Detects** the required Python version from each repo's metadata
7. **Creates** an isolated pyenv + venv environment per repository
8. **Executes** each notebook via `nbconvert`
9. **Compares** original vs. re-executed outputs
10. **Stores** all results in `output/db/db.sqlite`

---

## RRS Scoring — Repository Readiness

Each cloned repository is scored using the vendored [ReproScore](https://github.com/myVSR/reproscore) framework (see `pipeline/reproscore/`). The framework computes three complementary scores:

| Score | Description |
|---|---|
| **RRS** | Reproducibility Readiness Score — static analysis of repo artefacts (0–100) |
| **ROS** | Reproducibility Outcome Score — computed from execution evidence (0–100) |
| **RCS** | Reproducibility Composite Score — blends RRS and ROS via coverage weight α |

### RRS Categories

| Column | Category | Weight | τ | k | Sub-metrics |
|---|---|---|---|---|---|
| `score_E` | Environment Specification | 30% | 40 | 1.5 | dep_pinning, container_spec, env_bootstrap, python_version_declared |
| `score_A` | Data Accessibility | 25% | 30 | 1.5 | data_description, data_pointer, workflow_orchestration, data_acquisition_script |
| `score_D` | Documentation | 20% | 20 | 1.2 | doc_structure, install_instructions, usage_examples, inline_explanation_density, execution_entry_point, docstring_coverage, reuse_metadata |
| `score_C` | Code Portability | 15% | 25 | 1.2 | no_absolute_paths, import_resolvability, no_hardcoded_credentials, silent_failure_masking |
| `score_S` | Reproducibility Signals | 10% | 30 | 1.2 | seed_management, notebook_exec_order, test_file_presence, expected_outputs, ci_presence, config_externalised, hardware_requirements |
| `rrs` | **Total RRS** | — | — | — | Weighted composite with gate function and hard penalties |

### Gate Function

```
g(x, τ, k) = x / 100              if x ≥ τ
           = (x / τ)^k · (τ/100)  if x < τ
```

### Hard Penalties

| Condition | Penalty |
|---|---|
| E < 10 (no environment specification) | −20 pts |
| A < 10 (no data artefacts) | −15 pts |
| seed score < 50 (stochastic ops, no seeds) | −10 pts |

### Community Rubric

Override any weight or gate parameter via `config/default_rubric.yaml`:

```yaml
name: astrophysics-v1
version: "1.0"
categories:
  E: {weight: 0.30, tau: 40, k: 1.5}
  A: {weight: 0.25, tau: 30, k: 1.5}
  D: {weight: 0.20, tau: 20, k: 1.2}
  C: {weight: 0.15, tau: 25, k: 1.2}
  S: {weight: 0.10, tau: 30, k: 1.2}
```

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
bash run.sh --count 2          # process 2 repos at a time to avoid memory limits
```

Alternatively, use the Python entry point directly:

```bash
export ADS_API_TOKEN=your_ads_token_here
python3 pipeline/main.py collect
python3 pipeline/main.py mentions --limit 50
python3 pipeline/main.py run --count 2
```

For a single repo (interactive mode):

```bash
python3 pipeline/main.py run --interactive
# Enter GitHub URL when prompted
```

> **Note:** Git identity and environment variables reset between JupyterHub sessions. Re-export tokens and re-run `git config --global` after each login.

---

## Repository Structure

```
Reproducibility_Astro/
├── collect.sh               # Step 1 — stub: python3 -m pipeline collect
├── mentions.sh              # Step 2 — stub: python3 -m pipeline mentions
├── run.sh                   # Step 3 — stub: python3 -m pipeline run
├── binder/                  # repo2docker environment definition
│   ├── Dockerfile           # Full environment spec — Python, Jupyter, pyenv, nbdime
│   ├── apt.txt              # Additional system packages for pyenv build dependencies
│   └── postBuild            # Post-build script — configures pyenv PATH
├── config/
│   ├── config.py            # Pipeline configuration — paths, DB file, token helpers
│   └── default_rubric.yaml  # RRS rubric — weights, gate parameters, penalties
├── pipeline/                # All pipeline logic (Python)
│   ├── __main__.py          # Enables python3 -m pipeline
│   ├── main.py              # Entry point — subcommands: setup/collect/mentions/run/score/all
│   ├── runner.py            # Per-repo orchestration and batch processing
│   ├── db.py                # SQLite schema, CRUD helpers, CSV export
│   ├── env.py               # Python version detection, venv setup, notebook execution
│   ├── notebooks.py         # Notebook discovery and output comparison
│   ├── requirements.py      # Dependency extraction from notebooks and requirements files
│   ├── checks.py            # Pre-flight validation (git, repo URL)
│   ├── logger.py            # Logging utilities
│   ├── collect_ads.py       # NASA ADS collection + article categorisation
│   ├── extract_mentions.py  # arXiv LaTeX full-text mention extractor
│   ├── score.py             # RRS/ROS/RCS scoring — calls vendored reproscore
│   └── reproscore/          # Vendored ReproScore package (Sheeba Samuel, TU Chemnitz)
│       └── src/
│           ├── scoring/
│           │   ├── rrs.py       # RRSScorer — 26 sub-metrics, 5 categories
│           │   ├── ros.py       # ROSScorer — execution outcome score
│           │   ├── rcs.py       # RCSScorer — composite score (RRS + ROS)
│           │   └── rubric.py    # Rubric loader and validator
│           └── utils/
│               └── notebook_paths.py  # Notebook discovery and exclusion logic
├── analysis/
│   ├── astro_reproducibility_analysis.ipynb  # Main analysis notebook (4 RQs + ablation)
│   ├── compare_notebook.py  # Output comparison script — writes to notebook_executions
│   └── nbprocess/           # Notebook processing utilities
├── output/                  # All pipeline outputs (created at runtime, not committed)
│   ├── cloned_repos/        # Cloned repositories
│   ├── db/db.sqlite         # Single DB — all collection and execution results
│   ├── csv/                 # CSV exports of all tables
│   ├── logs/                # Per-repo execution logs
│   └── comparisons/         # JSON comparison reports
├── input/                   # Input repo lists for batch mode
└── tests/
    └── test_pipeline.sh     # Smoke test
```

---

## Setup

### Tokens required

| Token | Where to get it | Required for |
|---|---|---|
| `ADS_API_TOKEN` | [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu) → Account → Settings → API Token | `collect.sh` / `main.py collect` |
| `GITHUB_API_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens | `run.sh` / `main.py run` (batch mode) |

```bash
export ADS_API_TOKEN=your_ads_token_here
export GITHUB_API_TOKEN=your_github_token_here   # only needed for run
```

`mentions.sh` requires no API token.

### Dependencies

All dependencies are pre-installed by `binder/Dockerfile` when running on NFDI JupyterHub. If running locally:

```bash
pip install requests nbformat nbdime nbconvert pandas matplotlib seaborn scipy pyyaml
```

You also need Python 3.10+, SQLite3, Git, and pyenv installed on your system.

---

## Usage

### Step 1 — Collect papers

```bash
bash collect.sh
# or
python3 pipeline/main.py collect
```

Queries NASA ADS for astrophysics papers (last 2 months) mentioning Jupyter notebooks. Results are written to `output/db/db.sqlite`.

### Step 2 — Extract notebook mentions

```bash
bash mentions.sh --limit 10   # test with 10 articles
bash mentions.sh              # full run (rate-limited to 1 req/3s)
# or
python3 pipeline/main.py mentions --limit 10
```

For each article with an arXiv ID, fetches the LaTeX source tarball and extracts every notebook mention. Already-processed articles are skipped automatically.

### Step 3 — Run the pipeline

```bash
bash run.sh --count 2
# or
python3 pipeline/main.py run --count 2

# single repo (interactive):
python3 pipeline/main.py run --interactive
```

For each repo: clones it, scores with RRS/ROS/RCS, sets up an isolated Python environment, executes all notebooks, and compares outputs. Keep `--count` at 1–2 on JupyterHub to avoid memory limits.

### Step 4 — Analyse results

Open `analysis/astro_reproducibility_analysis.ipynb` in JupyterLab and run all cells. Covers all four research questions plus RRS ablation analysis.

### Full pipeline in one command

```bash
python3 pipeline/main.py all --count 2 --limit 50
```

---

## Database Schema

All data lives in `output/db/db.sqlite`.

### Collection tables (populated by `collect.sh` and `mentions.sh`)

| Table | Description |
|---|---|
| `journal` | One row per publication venue |
| `article` | One row per paper — includes `notebook_category`, `doi`, `subject` |
| `author` | One row per author |
| `repositories` | One row per extracted repo/URL — includes `host_type`, `notebook_count` |
| `notebook_mentions` | One row per in-text mention with context, section, link form, host |

### Execution tables (populated by `run.sh`)

| Table | Description |
|---|---|
| `repo_targets` | One row per processed repo — RRS/ROS/RCS scores, notebook paths, `paper_doi` |
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
| `jupyter_with_personal` | Jupyter/ipynb + personal/other website |
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
