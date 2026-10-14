FROM ghcr.io/astral-sh/uv:0.12.13-python3.14-alpine AS base

WORKDIR /app
ENV PYTHONPATH=/app

COPY pyproject.toml uv.lock README.md ./
COPY src/jouleverne ./jouleverne

RUN uv sync --no-install-project

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "jouleverne.app:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "125"]
