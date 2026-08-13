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

The API image also packages the evaluation datasets under
`/workspace/data/evaluation`, because the scheduled Airflow job runs the
evaluation script inside the API container.

The report includes faithfulness, answer relevancy, context precision, and
citation completeness. These are deliberately cheap RAGAS-style metrics; a
future judged evaluation can be added without changing the Q&A contract. The
retrieval evaluator reports Hit@K, Precision@K, Recall@K, MRR, nDCG@K, and
explicit document-coverage status for each case. The current five-case
semantic-hybrid smoke set is stored in MLflow after running the evaluation
inside the API container.

Set `MLFLOW_ENABLED=true` and configure `MLFLOW_TRACKING_URI` to log the same
run parameters and aggregate metrics to MLflow. The API image uses a small
REST fallback when the optional MLflow Python package is not installed. MLflow
remains disabled during normal user traffic.

## Evaluation improvement roadmap

The current-corpus retrieval file contains eight title-verified candidate
cases and is not a human- or legal-reviewed benchmark. The original four-case
file is retained as a historical coverage regression test. A quality benchmark
must first verify that its expected documents and versions exist in the
embedded corpus. A zero score with zero coverage is reported as a corpus/data
alignment problem; it does not measure ranking quality.

The next evaluation expansion is:

1. grow the reviewed set to at least 50 cases with direct lookup, dates,
   amendments, comparisons, multi-document synthesis, unsupported questions,
   bilingual wording, and hard negatives;
2. add article-level labels, version aliases, dataset hashes, and corpus
   fingerprints;
3. compare `--mode keyword`, `--mode semantic`, `--mode hybrid`, and optional
   reranked retrieval at K=1, 3, 5, and 10;
4. add reviewed answer/citation evaluation and optional bounded judge-model
   checks; and
5. add regression thresholds, coverage alerts, trend views, and sampled
   production queries.

The evaluator must keep corpus coverage, ranking quality, answer quality, and
operational health as separate dimensions.

## Scheduled evaluation

The Airflow daily DAG now runs discovery, processing, embedding, and retrieval
evaluation in order. The evaluation task uses the existing labeled dataset and
is protected by the same internal token boundary as the ingestion jobs.

Each retrieval evaluation writes an immutable JSON report under
`evaluation/retrieval/runs/` and updates `evaluation/retrieval/latest.json` in
the configured object store. Authenticated users can read the latest report at
`/evaluation/retrieval/latest`. When MLflow is enabled, aggregate ranking and
corpus-coverage metrics are logged to the `retrieval-evaluation` run as well.
This keeps the numeric result available even when Airflow task logs are
unavailable.
