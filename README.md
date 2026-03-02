# Containing the Reproducibility Gap

**Automated Repository-Level Containerization for Scholarly Jupyter Notebooks**

[![License: GPL-3.0 license](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)

## Overview

This repository contains an automated, web-scale reproducibility engineering pipeline that systematically assesses and improves the computational reproducibility of Jupyter notebooks linked to scholarly publications. The pipeline introduces **repository-level containerization**, encapsulating entire research repositories—including all notebooks, dependencies, and execution contexts—within Docker containers to enable consistent, isolated, and repeatable execution across heterogeneous systems.

### Key Features

- 🔄 **Automated Dependency Extraction**: Parses `requirements.txt`, `setup.py`, and statically analyzes notebook import statements
- 🐳 **Repository-Level Dockerization**: Generates custom Docker images for each repository
- 📊 **Cell-Level Reproducibility Assessment**: Compares original vs. re-executed outputs using `nbdime`
- 📈 **Structured Logging**: SQLite database tracking execution metadata, errors, and reproducibility metrics
- 🔍 **Fine-Grained Error Categorization**: Systematic taxonomy of failure modes

## Architecture

The pipeline operates through four automated stages:
```
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: Repository Discovery & Validation                     │
│  • Clone from GitHub                                             │
│  • Validate availability and Python notebook presence            │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│  Stage 2: Autonomous Environment Inference                      │
│  • Parse requirements.txt, setup.py                              │
│  • Extract imports from notebooks 
│  • Generate consolidated requirements.txt                        │
│  • Build repository-specific Dockerfile                          │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│  Stage 3: Containerized Execution                               │
│  • Build Docker image with dependencies                          │
│  • Execute notebooks via nbconvert --execute --allow-errors      │
│  • Capture outputs, logs, and execution metadata                 │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│  Stage 4: Reproducibility Assessment                            │
│  • Compare original vs. re-executed outputs (nbdime)             │
│  • Compute cell-level reproducibility scores                     │
│  • Store results in SQLite database                              │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- **Docker** 20.10+ ([Install Docker](https://docs.docker.com/get-docker/))
- **Python** 3.10+ with pip
- **Git** 2.30+
- **SQLite** 3.35+
- **Bash** 4.0+

### Setup
```bash
# Clone the repository
git clone https://github.com/Sheeba-Samuel/computational-reproducibility-pmc-docker.git
cd computational-reproducibility-pmc-docker

# Install Python dependencies
pip install -r requirements.txt

# Make the main script executable
chmod +x main.sh
```

### Configuration

Edit `config.sh` to customize:
```bash
# Paths
DB_FILE="data/db/db.sqlite"
LOGS_DIR="data/logs"

```

## Usage

### Quick Start
```bash
cd scripts
# Process a single repository
./main.sh 

```

## Database Schema

The pipeline maintains a normalized SQLite schema:

### Core Tables

- **`repositories`**: Repository metadata (URL, notebook count, requirements status)
- **`repository_runs`**: Execution runs with timestamps, status, and resource metrics
- **`notebook_executions`**: Per-notebook execution results, errors, and cell counts
- **`notebook_reproducibility_metrics`**: Cell-level reproducibility scores and comparisons

### Example Queries
```sql
-- Repositories with highest reproducibility scores
SELECT r.repository, AVG(nrm.reproducibility_score) as avg_score
FROM repositories r
JOIN notebook_reproducibility_metrics nrm ON r.id = nrm.repository_id
GROUP BY r.id
ORDER BY avg_score DESC
LIMIT 10;

-- Most common error types
SELECT error_type, COUNT(*) as count
FROM notebook_executions
WHERE execution_status NOT IN ('SUCCESS', 'SUCCESS_WITH_ERRORS')
GROUP BY error_type
ORDER BY count DESC;

-- Success rate by requirements.txt presence
SELECT 
    CASE WHEN requirements IS NOT NULL THEN 'With requirements.txt' 
         ELSE 'Without requirements.txt' END as req_status,
    COUNT(*) as total,
    SUM(CASE WHEN run_status = 'SUCCESS' THEN 1 ELSE 0 END) as successful
FROM repositories r
JOIN repository_runs rr ON r.id = rr.repository_id
GROUP BY req_status;
```


## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Commit your changes**: `git commit -m 'Add amazing feature'`
4. **Push to the branch**: `git push origin feature/amazing-feature`
5. **Open a Pull Request**


### Related Publications

- Samuel, S., & Mietchen, D. (2024). Computational reproducibility of Jupyter notebooks from biomedical publications. *GigaScience*, 13, giad113. [DOI: 10.1093/gigascience/giad113](https://doi.org/10.1093/gigascience/giad113)
- Sheeba Samuel and Daniel Mietchen. FAIR Jupyter: A Knowledge Graph Approach to Semantic Sharing and Granular Exploration of a Computational Notebook Reproducibility Dataset. In Special Issue on Resources for Graph Data and Knowledge. Transactions on Graph Data and Knowledge (TGDK), Volume 2, Issue 2, pp. 4:1-4:24, Schloss Dagstuhl – Leibniz-Zentrum für Informatik (2024) [DOI: 10.4230/TGDK.2.2.4](https://doi.org/10.4230/TGDK.2.2.4).
- Samuel, S., & Mietchen, D. (2023). Dataset of a study of computational reproducibility of Jupyter notebooks from biomedical publications. *Zenodo*. [DOI: 10.5281/zenodo.8226725](https://doi.org/10.5281/zenodo.8226725)

## Acknowledgments

This research was supported by:
- **Jupyter4NFDI** project (DFG 567156310)
- **find.software** project (DFG 567156310)
- **MaRDI** project (DFG 460135501)
- **SeDOA** project (DFG 556323977)
- **HYP*MOL** project (DFG 514664767)

Special thanks to the open-source community and contributors to Docker, Jupyter, nbdime, and related tools.

## License

This project is licensed under the GPL-3.0 license - see the [LICENSE](LICENSE) file for details.

## Contact

For questions, issues, or collaboration opportunities:

- **GitHub Issues**: [github.com/Sheeba-Samuel/computational-reproducibility-pmc-docker/issues](https://github.com/Sheeba-Samuel/computational-reproducibility-pmc-docker/issues)
- **Email**: sheeba.samuel@informatik.tu-chemnitz.de
- **Research Group**: [Distributed and Self-organizing Systems, TU Chemnitz](https://vsr.informatik.tu-chemnitz.de/)

---

**Repository**: [https://github.com/Sheeba-Samuel/computational-reproducibility-pmc-docker](https://github.com/Sheeba-Samuel/computational-reproducibility-pmc-docker)  
**Dataset**: [Zenodo 10.5281/zenodo.8226725](https://doi.org/10.5281/zenodo.8226725)