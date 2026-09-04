FROM python:3.14-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# Migrations are copied after the install so editing a revision does not
# invalidate the dependency layer.
COPY alembic.ini ./
COPY migrations ./migrations

RUN useradd -r -u 1001 argus
USER argus

ENTRYPOINT ["argus"]

# Test/lint image: the runtime install deliberately omits dev dependencies, so
# pytest and ruff are only available here. Used by the `test` compose service.
FROM base AS dev

USER root
RUN pip install --no-cache-dir ".[dev]"
USER argus
