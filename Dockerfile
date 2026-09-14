# Ursula HTTP API.
#
#   docker build -t ursula .
#   docker run --rm -p 8000:8000 -e URSULA_MAILTO=you@vt.edu ursula

FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so source edits don't invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra http

COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --extra http


FROM python:3.12-slim

RUN useradd --system --uid 10001 --no-create-home ursula

COPY --from=build /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER ursula
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["ursula", "serve", "--host", "0.0.0.0", "--port", "8000"]
