# syntax=docker/dockerfile:1
# ============================================================
# Builder stage: install dependencies with uv
# ============================================================
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock ./

# Install project dependencies into a virtual environment inside /app/.venv
RUN uv sync --frozen --no-install-project --no-dev

# ============================================================
# Runtime stage
# ============================================================
FROM python:3.12-slim AS runtime

# Create non-root user and group
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy installed virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Activate the virtual environment by prepending it to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY entrypoint.sh ./

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8000

# Health check using Python's built-in urllib to avoid curl dependency
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" \
    || exit 1

# Use entrypoint script to run migrations then start server
ENTRYPOINT ["./entrypoint.sh"]
