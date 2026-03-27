FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    sqlite3 \
    curl \
    ca-certificates \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install Docker
RUN curl -fsSL https://get.docker.com | sh

# Install repo2docker and pipeline dependencies
RUN pip install --no-cache-dir \
    jupyter-repo2docker \
    GitPython \
    jupyterlab \
    nbconvert \
    nbdime \
    nbformat \
    nbclient \
    matplotlib \
    numpy \
    pandas \
    scipy \
    seaborn \
    requests

# Required for Binder/NFDI to work
ARG NB_USER
ARG NB_UID
ENV USER=${NB_USER}
ENV HOME=/home/${NB_USER}

RUN adduser --disabled-password \
    --gecos "Default user" \
    --uid ${NB_UID} \
    ${NB_USER}

WORKDIR ${HOME}
