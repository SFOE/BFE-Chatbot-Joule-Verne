# Stage 1: Install dependencies (has build tools)
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    git \
    build-essential \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final image (no build tools)
FROM python:3.11-slim

WORKDIR /app

# Upgrade OS packages to get security patches, install only runtime deps
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Upgrade pip in final image to fix pip CVEs
RUN pip install --upgrade pip setuptools wheel

# Copy application code
COPY . .

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "agent.py", "--server.port=8501", "--server.address=0.0.0.0"]
