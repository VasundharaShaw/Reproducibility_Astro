# Quickstart Guide

This guide gets you from zero to a first pipeline run in under 5 minutes on NFDI JupyterHub.

---

## Step 1 — Launch the environment

1. Go to [hub.nfdi-jupyter.de](https://hub.nfdi-jupyter.de/hub/home)
2. Click **Start Server** → select **Repo2docker (Binder)**
3. Fill in:
   - **Repository URL**: `https://github.com/VasundharaShaw/CPRPMC-pyenv-Vasu`
   - **Git ref**: `main`
   - **Flavor**: `4GB RAM, 1 vCPU` (minimum)
4. Click **Start** and wait for the build to finish (~2 min on first launch)

---

## Step 2 — Run the pipeline

Open a terminal in JupyterLab and run:

```bash
cd scripts
bash main.sh
```

You will see:

```
Would you like to input a custom GitHub repo or use the SQLite flow?
1. Input custom GitHub repo
2. Use SQLite flow
Enter your choice (1 or 2):
```

---

## Step 3 — Choose a mode

### Mode 1 — Test with a single repo (recommended for first run)

Enter `1` and use one of the sample repos from `data/sample_repos.txt`.

**Example — simple repo:**
```
Enter GitHub repo URL:
  https://github.com/ncbi/elastic-blast-demos

Enter notebook paths (semicolon-separated):
  elastic-blast-rdrp.ipynb

Enter setup paths (semicolon-separated, optional):
  [press Enter to skip]

Enter requirements paths (semicolon-separated, optional):
  requirements.txt
```

The pipeline will clone the repo, set up a pyenv environment, execute the notebook, compare outputs, and write results to the database.

### Mode 2 — Batch run (SQLite flow)

Enter `2` to process up to 10 unexecuted repositories already registered in `data/db/db.sqlite`. This is the main mode for large-scale studies.

---

## Step 4 — View results

Once the pipeline finishes, open `analysis/analyse_reporesults.ipynb` in JupyterLab to explore the results interactively.

Or query the database directly in a terminal:

```bash
cd data/db
sqlite3 db.sqlite "SELECT repository, run_status FROM repository_runs LIMIT 10;"
```

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `pyenv: command not found` | postBuild didn't run | Re-launch via repo2docker (not plain JupyterHub) |
| `ModuleNotFoundError` in notebook | Missing dependency in target repo | Check `data/logs/` for the error details |
| `sqlite3: command not found` | System package missing | Should not happen with repo2docker; re-launch |
| Pipeline hangs on a notebook | Notebook has infinite loop or blocking cell | Check `data/logs/` — pipeline will eventually time out |
