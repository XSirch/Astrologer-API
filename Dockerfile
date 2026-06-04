# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder stage: install dependencies with uv
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first (enables layer caching)
COPY pyproject.toml uv.lock ./

# Install only production dependencies into .venv
RUN uv sync --frozen --no-dev --no-install-project

# ---------------------------------------------------------------------------
# Runtime stage: minimal image, non-root user
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Create a non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Bring in the pre-built virtualenv from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy only the application source
COPY app/ ./app/

# Put the venv on PATH so uvicorn is available without activation
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV_TYPE=production

USER appuser

EXPOSE 8080

# 2 workers is a safe default; override with --workers N at runtime
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
