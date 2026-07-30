# ------------------------------------------------------------
# Dockerfile for ADELIA Content Engine Microservice
# ------------------------------------------------------------
FROM python:3.12-slim

# ---------- System dependencies ----------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# ---------- Create non-root user ----------
RUN useradd -m -u 1000 appuser

# ---------- Working directory ----------
WORKDIR /app

# ---------- Install Python dependencies ----------
# Lean, serverless dependencies (sqlite-vec prebuilt wheel; NO torch, NO transformers)
COPY adelia/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Copy application source ----------
COPY adelia/ ./adelia/

# ---------- Set environment & non-root user ----------
ENV PYTHONPATH=/app
# USER appuser

# ---------- Entrypoint ----------
# Bound to 0.0.0.0:8001 inside container (internal network only)
CMD ["uvicorn", "adelia.main:app", "--host", "0.0.0.0", "--port", "8001"]
