FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_HTTP_TIMEOUT=120
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY services/product-service/pyproject.toml services/product-service/

RUN uv venv /app/.venv
RUN uv sync --package product-service --frozen --no-dev

COPY . .

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/services /app/services
COPY --from=builder /app/shared /app/shared

ENV PATH="/app/.venv/bin:$PATH"

# Include /app so `from shared.telemetry import ...` resolves.
ENV PYTHONPATH="/app/services/product-service:/app"

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
  CMD python -c "import socket; s=socket.create_connection(('localhost',50051),timeout=3); s.close()" || exit 1

CMD ["python", "services/product-service/main.py"]
