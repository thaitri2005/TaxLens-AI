FROM python:3.12-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/src \
    HF_HUB_DISABLE_TELEMETRY=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-vie tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY docs/local-development.md ./docs/local-development.md
COPY src ./src
COPY scripts ./scripts
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1+cpu
RUN pip install --no-cache-dir ".[dev]"

ARG EMBEDDING_MODEL_ID=intfloat/multilingual-e5-small
ARG EMBEDDING_MODEL_REVISION=614241f622f53c4eeff9890bdc4f31cfecc418b3
ENV EMBEDDING_MODEL_ID=${EMBEDDING_MODEL_ID} \
    EMBEDDING_MODEL_REVISION=${EMBEDDING_MODEL_REVISION} \
    EMBEDDING_MODEL_PATH=/opt/taxlens-models/multilingual-e5-small
RUN python -c "import os; from huggingface_hub import snapshot_download; snapshot_download(repo_id=os.environ['EMBEDDING_MODEL_ID'], revision=os.environ['EMBEDDING_MODEL_REVISION'], local_dir=os.environ['EMBEDDING_MODEL_PATH'])"

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8000

CMD ["uvicorn", "taxlens.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
