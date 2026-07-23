# Joule Verne API

Backend API for the BFE Joule Verne chatbot. Built with FastAPI, deployed on ECS.

## Setup

```bash
# Install dependencies
uv sync

# Copy environment config
cp env.example .env
# Fill in your AWS credentials and agent IDs
```

## Run locally

```bash
uv run uvicorn jouleverne.app:app --reload
```

The API will be available at `http://localhost:8000`.

## Run with Docker

```bash
docker compose up --build
```

## Test

```bash
uv run pytest
```

## Health check

```
GET /v1/health → {"status": "ok"}
```
