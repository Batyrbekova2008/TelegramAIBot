# Multi-stage build (Task 29)
# Stage 1: builder — install dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps for psycopg2 and edge-tts
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: runtime — minimal image
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN useradd --create-home --shell /bin/bash botuser

WORKDIR /app

# System runtime deps (libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/botuser/.local

# Copy application code
COPY --chown=botuser:botuser . .

# Create data directory
RUN mkdir -p /app/data && chown botuser:botuser /app/data

USER botuser

# Add local bin to PATH (for pip --user installed packages)
ENV PATH=/home/botuser/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check — verify python can import main modules
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "from config.settings import config; print('ok')" || exit 1

EXPOSE 8443

CMD ["python", "main.py"]
