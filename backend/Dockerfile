# Backend image: FastAPI API, arq worker and scheduler share it (entrypoint differs per compose service).
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git docker-cli \
    && rm -rf /var/lib/apt/lists/*
# Node is required by the Claude Agent SDK's bundled `claude` CLI subprocess.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/backend
COPY pyproject.toml ./
RUN pip install uv && uv pip install --system -e . 2>/dev/null || true
COPY . .
RUN uv pip install --system -e ".[dev]"
RUN useradd -u 10000 -m app && mkdir -p /data && chown -R app:app /data /srv/backend
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
