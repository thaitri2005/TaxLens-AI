FROM python:3.12-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/src \
    HF_HUB_DISABLE_TELEMETRY=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-vie tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/api-runtime.txt ./requirements/api-runtime.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1+cpu
RUN pip install --no-cache-dir -r requirements/api-runtime.txt

ARG EMBEDDING_MODEL_ID=intfloat/multilingual-e5-small
ARG EMBEDDING_MODEL_REVISION=614241f622f53c4eeff9890bdc4f31cfecc418b3
ENV EMBEDDING_MODEL_ID=${EMBEDDING_MODEL_ID} \
    EMBEDDING_MODEL_REVISION=${EMBEDDING_MODEL_REVISION} \
    EMBEDDING_MODEL_PATH=/opt/taxlens-models/multilingual-e5-small
RUN python -c "import os; from huggingface_hub import snapshot_download; snapshot_download(repo_id=os.environ['EMBEDDING_MODEL_ID'], revision=os.environ['EMBEDDING_MODEL_REVISION'], local_dir=os.environ['EMBEDDING_MODEL_PATH'])"

COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY src ./src
COPY scripts ./scripts
COPY data/evaluation ./data/evaluation

# Tesseract's OpenMP threads contend with each other on the 1-vCPU container and slow OCR
# down; one thread per process is faster there.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    OMP_THREAD_LIMIT=1

# The commit the image was built from; evaluation reports record it (no git in the image).
ARG TAXLENS_CODE_VERSION=
ENV TAXLENS_CODE_VERSION=${TAXLENS_CODE_VERSION}

EXPOSE 8000

# The API runs as a single replica, so it applies pending migrations itself. They run in a
# background thread after uvicorn starts (see taxlens/api/migrations.py): /health answers
# the liveness probe at once and /ready stays 503 until the schema is current.
ENV RUN_MIGRATIONS_ON_STARTUP=true

CMD ["uvicorn", "taxlens.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
