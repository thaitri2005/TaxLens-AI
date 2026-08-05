# Airflow local profile

Airflow is the scheduled-ingestion component for TaxLens. The daily DAG calls
the existing idempotent commands in order:

```text
discover and ingest → process and OCR → embed pending chunks → evaluate retrieval
```

The normal PostgreSQL/API/web profile remains unchanged. Start the scheduler
profile explicitly after the API image has been built:

```powershell
docker compose --profile airflow up -d airflow-postgres airflow-init airflow-scheduler airflow-webserver
```

Open `http://localhost:8080` and sign in with the credentials in `.env` or the
Compose defaults. Trigger `tax_regulation_discovery_daily` manually for a
smoke test, then inspect task logs and retry behavior.

Airflow has its own Python environment because Airflow and the API use
different SQLAlchemy compatibility ranges. The DAG calls four allowlisted
internal API job endpoints over the Compose network using
`X-TaxLens-Internal-Token`; the API executes the existing scripts in its own
runtime, preserving Tesseract and the baked-in embedding model. No Docker
socket is exposed to Airflow. For M6, these endpoints can be replaced by
Container Apps Jobs without changing the DAG task boundaries.
