# ------------------------------------------------------------
# Dockerfile for AuraOne (router / monolith)
# ------------------------------------------------------------
FROM python:3.11-slim

# ---------- System dependencies (only if needed) ----------
# Build tools required for compiling some Python packages (e.g., lxml, pandas)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# ---------- Create a non‑root user ----------
RUN useradd -m -u 1000 appuser

# ---------- Working directory ----------
WORKDIR /app

# ---------- Install Python dependencies ----------
# Copy lock file and install exact versions
COPY AuraOne/requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt

# ---------- Copy application source ----------
COPY AuraOne/ ./AuraOne/
COPY AuraOne/.env.example ./AuraOne/.env.example

# ---------- Set non‑root user ----------
USER appuser

# ---------- Entrypoint ----------
# The real entrypoint is AuraOne/main.py (starts the Telegram bot)
CMD ["python", "AuraOne/main.py"]
