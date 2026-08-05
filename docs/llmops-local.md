# Local LLMOps workflow

M5.5 keeps the production request path inexpensive while making the workflow
observable and evaluable.

## Runtime path

The Q&A request is executed by a LangGraph state graph:

```text
plan query → retrieve evidence → assess evidence → generate answer
```

Unsupported questions and insufficient evidence exit before inference. The
existing provider-neutral `ChatProvider` contract remains the business
boundary. `LangChainChatAdapter` wraps the configured Hugging Face provider so
the provider can be replaced without changing retrieval or API routes.

## Evaluation path

Install the optional evaluation dependencies when working on experiment
tracking:

```powershell
python -m pip install -e ".[dev,llmops]"
```

Run the deterministic, no-judge-model evaluation locally:

```powershell
$env:PYTHONPATH = "src"
python scripts/evaluate_qa.py
```

The API image contains the embedding model at
`/opt/taxlens-models/multilingual-e5-small`; a host Python environment usually
does not. If the model is not present locally, the script reports that fact and
falls back to keyword retrieval. Use `--keyword-only` explicitly for a fast
host-side smoke run. Keyword-only results are not comparable to the normal
semantic-hybrid production path and may return insufficient evidence for
Vietnamese queries with spelling or diacritic variation.

The report includes faithfulness, answer relevancy, context precision, and
citation completeness. These are deliberately cheap RAGAS-style metrics; a
future judged evaluation can be added without changing the Q&A contract.

Set `MLFLOW_ENABLED=true` and configure `MLFLOW_TRACKING_URI` to log the same
run parameters and aggregate metrics to MLflow. MLflow remains disabled during
normal user traffic.

## Scheduled evaluation

The Airflow daily DAG now runs discovery, processing, embedding, and retrieval
evaluation in order. The evaluation task uses the existing labeled dataset and
is protected by the same internal token boundary as the ingestion jobs.
