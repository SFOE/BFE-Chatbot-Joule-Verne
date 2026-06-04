# ─── Stage 1: build ──────────────────────────────────────────────────────────
# build-essential (and its perl dependency) stays here and never reaches runtime
FROM python:3.11-slim AS builder

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade wheel (fixes CVE-2026-24049) and setuptools (fixes CVE-2026-23949 via
# updated vendored jaraco.context) before installing project requirements
RUN pip install --no-cache-dir --upgrade pip "wheel>=0.46.2" setuptools

RUN pip install --no-cache-dir -r requirements.txt

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
# Fresh base: no build tools, no perl, no git (GitPython is not used by the app).
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Upgrade system Python packaging tools BEFORE activating the venv so that
# /usr/local/bin/pip is used — the venv pip would otherwise shadow it.
# This fixes pip (CVE-2025-8869, CVE-2026-6357, CVE-2026-3219, CVE-2026-1703),
# wheel (CVE-2026-24049), and setuptools-vendored jaraco.context (CVE-2026-23949).
# Purge the full `perl` package: no fix version exists (all perl CVEs show null),
# and perl is not required at runtime; perl-base (Required) stays.
RUN pip install --no-cache-dir --upgrade pip "wheel>=0.46.2" setuptools \
    && apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get purge -y --auto-remove perl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH"

COPY . .

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "agent.py", "--server.port=8501", "--server.address=0.0.0.0"]
