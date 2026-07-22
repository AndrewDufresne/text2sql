FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Contracts package is copied in via build context (see compose 50-app.yml).
# Build context = services/langgraph-app, but we need the contracts package too;
# we vendor it via a relative copy at build time (see Makefile for prep step).
COPY pyproject.toml ./
COPY app ./app
COPY vendor/text2sql-contracts ./vendor/text2sql-contracts

RUN pip install ./vendor/text2sql-contracts && \
    pip install -e .

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8080/healthz').status==200 else sys.exit(1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
