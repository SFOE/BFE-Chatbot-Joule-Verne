FROM ghcr.io/astral-sh/uv:0.12.13-python3.14-alpine AS base

WORKDIR /app
# Build the venv at an explicit path so we can run from it directly once the
# uv binary is removed from the final image.
ENV PYTHONPATH=/app \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock README.md ./
COPY src/jouleverne ./jouleverne

RUN uv sync --no-install-project

# Remove the uv/uvx binaries from the final image. They are only needed at build
# time; keeping them pulls in vulnerable Rust crates (quinn-proto, rustls, h2, rsa)
# that the scanner flags on /usr/local/bin/uv. The app runs directly from the venv.
RUN rm -f /usr/local/bin/uv /usr/local/bin/uvx

# Run uvicorn directly from the venv instead of `uv run`.
ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

EXPOSE 8000

CMD ["uvicorn", "jouleverne.app:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "125"]
