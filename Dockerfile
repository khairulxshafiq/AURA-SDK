# ============================================================
# Dockerfile — aura-router (Master Gateway / Monolith)
# ============================================================
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer outputs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/AuraOne

WORKDIR /app

# Install system build dependencies required for lxml and cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libxml2-dev \
    libxslt-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY AuraOne/requirements.txt /app/AuraOne/requirements.txt
RUN pip install --no-cache-dir -r AuraOne/requirements.txt

# Copy source files
COPY . /app

# Verified Entrypoint (AGENTS.md audit confirmed main.py)
CMD ["python", "AuraOne/main.py"]
