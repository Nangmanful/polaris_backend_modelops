# Build stage
FROM ubuntu:22.04 AS builder

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

WORKDIR /app

# Install Python 3.11 and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    gpg \
    gpg-agent \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-distutils \
    gdal-bin \
    libgdal-dev \
    libhdf5-dev \
    libnetcdf-dev \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml README.md ./

# Install dependencies with Python 3.11
RUN uv pip install --python python3.11 --system --no-cache . && \
    python3.11 -c "import sys; print('Site-packages:', sys.path)"

# Production stage
FROM ubuntu:22.04 AS production

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

WORKDIR /app

# Install Python 3.11 and runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    gpg \
    gpg-agent \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    python3.11 \
    gdal-bin \
    libgdal30 \
    libhdf5-103-1 \
    libnetcdf19 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/lib/python3.11 /usr/lib/python3.11
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY main.py .
COPY modelops/ ./modelops/

# ESG Trends Agent 추가
COPY src ./src
COPY scripts ./scripts

# Create logs directory for ESG agent
RUN mkdir -p /app/logs

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose port for FastAPI
EXPOSE 8001

# Environment variables
ENV PYTHONUNBUFFERED=1

# Health check for FastAPI
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3.11 -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/health', timeout=5)" || exit 1

# Run the FastAPI application with uvicorn
CMD ["python3.11", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"]
