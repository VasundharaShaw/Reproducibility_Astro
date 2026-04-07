FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV NB_USER=jovyan
ENV NB_UID=1000
ENV HOME=/home/${NB_USER}

# ---------------------------------------------------------------
# System packages — includes pyenv build dependencies
# ---------------------------------------------------------------
RUN apt-get update -qq && \
    apt-get install -qq --yes --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        git \
        sqlite3 \
        make \
        build-essential \
        libssl-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libffi-dev \
        liblzma-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------
# Create jovyan user (matches NFDI expectation)
# ---------------------------------------------------------------
RUN groupadd --gid ${NB_UID} ${NB_USER} && \
    useradd \
        --comment "Default user" \
        --create-home \
        --gid ${NB_UID} \
        --no-log-init \
        --shell /bin/bash \
        --uid ${NB_UID} \
        ${NB_USER}

# ---------------------------------------------------------------
# Install Miniconda — using conda-forge channel only
# ---------------------------------------------------------------
ENV CONDA_DIR=/opt/conda
ENV PATH=${CONDA_DIR}/bin:${PATH}

RUN wget -qO /tmp/miniconda.sh \
        https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && \
    bash /tmp/miniconda.sh -b -p ${CONDA_DIR} && \
    rm /tmp/miniconda.sh && \
    conda config --system --prepend channels conda-forge && \
    conda config --system --remove channels defaults || true && \
    conda config --system --set channel_priority strict && \
    conda clean -afy

# ---------------------------------------------------------------
# Install Jupyter via conda-forge (no defaults channel)
# ---------------------------------------------------------------
RUN conda install -y -c conda-forge \
        python=3.10 \
        notebook \
        jupyterlab \
        nbconvert \
    && conda clean -afy

# ---------------------------------------------------------------
# Install pyenv as jovyan user
# ---------------------------------------------------------------
USER ${NB_USER}

ENV PYENV_ROOT=${HOME}/.pyenv
ENV PATH=${PYENV_ROOT}/bin:${PYENV_ROOT}/shims:${PATH}

RUN curl https://pyenv.run | bash && \
    pyenv --version

# ---------------------------------------------------------------
# Copy repo files in and set working directory
# ---------------------------------------------------------------
COPY --chown=${NB_USER}:${NB_USER} . ${HOME}

WORKDIR ${HOME}
