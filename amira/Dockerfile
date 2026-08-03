# AMIRA Trading Engine — Dockerfile
# Runs the FastAPI advisory service on port 8000 (internal network only).
# NOT exposed to the public internet — aura-app reaches it at http://amira-app:8000.

FROM python:3.12-slim

# --- system deps for pandas / pandas-ta / llvmlite (numba) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies first (layer cache)
COPY amira/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire amira service package
COPY amira/ ./amira/

# Data directory — mapped as a named volume at runtime
RUN mkdir -p /app/data

# Expose internal port (no host mapping in compose)
EXPOSE 8000

# Run with uvicorn — single worker is fine for a Telegram-volume advisory service
CMD ["uvicorn", "amira.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
