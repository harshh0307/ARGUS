FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

ENTRYPOINT ["argus"]
