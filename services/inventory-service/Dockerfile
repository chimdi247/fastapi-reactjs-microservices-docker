FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY services/inventory-service/pyproject.toml services/inventory-service/
RUN uv sync --package inventory-service --frozen --no-dev
COPY . .

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

# Include /app so `from shared.telemetry import ...` resolves.
ENV PYTHONPATH="/app/services/inventory-service:/app"
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/readiness')" || exit 1

CMD ["fastapi", "run", "services/inventory-service/main.py", "--port", "8000", "--host", "0.0.0.0"]
