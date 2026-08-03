FROM python:3.12-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/src

COPY pyproject.toml ./
COPY docs/local-development.md ./docs/local-development.md
COPY src ./src
RUN pip install --no-cache-dir ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "taxlens.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
