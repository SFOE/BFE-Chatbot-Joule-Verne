# Stage 1: Install dependencies (has build tools)
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final image (no build tools, smaller and safer)
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install only runtime dependencies (no compilers/build tools)
RUN apt-get update && apt-get install -y \
    git \
    libffi8 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "agent.py", "--server.port=8501", "--server.address=0.0.0.0"]
