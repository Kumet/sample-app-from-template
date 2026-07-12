FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    git \
    make \
    curl \
    ca-certificates \
    python3 \
    python3-pip \
    pipx \
  && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:${PATH}"
