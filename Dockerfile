# ─── Stage 1: Build frontend ─────────────────────────────────────────────────
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build-only

# ─── Stage 2: Build backend ──────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:0.12.13-python3.14-alpine AS base

# Patch Alpine system packages (openssl, musl, xz, util-linux CVEs)
RUN apk update && apk upgrade --no-cache

WORKDIR /app

# Build the venv at an explicit path so we can run from it directly once the
# uv binary is removed from the final image.
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# Install backend dependencies
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --no-install-project --frozen

# Upgrade pip to fix CVE-2026-8643, CVE-2026-6357, CVE-2026-3219, CVE-2026-13346
RUN uv pip install "pip==26.2.1"

# Copy backend source
COPY backend/src/ ./src/

# Copy built frontend static files
COPY --from=frontend-build /app/frontend/dist ./static

# Copy scripts and fetch release notes at build time (writes /app/release_notes.json)
COPY scripts/ ./scripts/
ARG GITHUB_TOKEN=""
RUN uv run --no-project python scripts/fetch_releases.py || true

# Remove the uv/uvx binaries from the final image. They are only needed at build
# time; keeping them pulls in vulnerable Rust crates (quinn-proto, rustls, h2, rsa)
# that the scanner flags on /usr/local/bin/uv. The app runs directly from the venv.
RUN rm -f /usr/local/bin/uv /usr/local/bin/uvx

# Run uvicorn directly from the venv instead of `uv run`.
ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

# Run as a non-root user (hardening).
RUN adduser -D -u 1000 appuser \
    && chown -R 1000:1000 /app
USER 1000

EXPOSE 8000

CMD ["uvicorn", "jouleverne.app:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "125", "--app-dir", "src"]
