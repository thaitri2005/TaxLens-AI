# Evaluation

TaxLens measures retrieval and answers with deterministic, inexpensive checks that need
no judge model. Datasets are versioned in `data/evaluation` (label format in
[data/evaluation/README.md](../data/evaluation/README.md)).

## Retrieval

`scripts/evaluate_tax_retrieval.py` runs the default dataset,
`tax_article_retrieval.json`: 18 answerable Vietnamese questions (four typed without
diacritics), each labelled with the document **and article** that answers it, plus two
out-of-corpus questions that the ranking metrics skip.

```powershell
docker compose exec -T api python scripts/evaluate_tax_retrieval.py
docker compose exec -T api python scripts/evaluate_tax_retrieval.py --mode keyword
```

It reports, at K = 1, 3, 5, and 10: hit rate, precision, recall, mean reciprocal rank,
nDCG, and the article-level `mean_article_hit_at_k` and `mean_article_reciprocal_rank`.
`--mode` compares `keyword`, `semantic`, and `hybrid` on the same corpus.

Each report records the dataset hash, a corpus fingerprint, and whether the labelled
documents are embedded. A case whose expected document is missing is reported as not
covered rather than as a ranking failure, and a run with no covered case is
`not_evaluable`.

Reports are written to object storage under `evaluation/retrieval/runs/`, with the latest
also at `evaluation/retrieval/latest.json` and served by `GET /evaluation/retrieval/latest`.
The daily DAG runs this evaluation after embedding.

Measured results are in [retrieval.md](retrieval.md#7-measured-effect). They were
measured on the five curated documents plus four unrelated decrees, before the corpus grew
to about 1,700 documents; with many more competing passages, ranks will differ, so rerun
the evaluation before quoting them.

## Answers

`scripts/evaluate_qa.py` runs the five questions in `qa.json` through the full Q&A
pipeline and reports:

| Metric | Meaning |
| --- | --- |
| Faithfulness | Share of confirmed facts whose citations all refer to provided passages |
| Answer relevancy | Word overlap between the answer and the question |
| Context precision | Word overlap between the question and the retrieved passages |
| Citation completeness | Share of confirmed facts that cite at least one valid passage |

These are lexical, RAGAS-style approximations. They need a working answer model
(`HF_TOKEN` with credits). Outside the API container the embedding model is usually
missing; the script then says so and falls back to keyword retrieval, or use
`--keyword-only` for a quick smoke run. Keyword-only scores are not comparable with the
hybrid production path.

## MLflow

Set `MLFLOW_ENABLED=true` and `MLFLOW_TRACKING_URI` to log run parameters and aggregate
metrics (experiment `MLFLOW_EXPERIMENT_NAME`). Start a local server with
`docker compose --profile llmops up -d mlflow`. The API image logs through a small REST
client when the MLflow package is not installed. MLflow is never on the request path.

## Q&A pipeline

The answer path is a LangGraph state graph:

```text
plan query → retrieve evidence → assess evidence → generate answer → validate
```

Out-of-scope questions and insufficient evidence end before the model is called. The
model is reached through a provider-neutral `ChatProvider` interface, wrapped by
`LangChainChatAdapter`, so another provider needs no change to retrieval or the API.

## Next steps

1. Relabel and grow the article dataset against the full corpus (at least 50 cases:
   direct lookups, dates, amendments, comparisons, multi-document questions, unanswerable
   questions, text without diacritics, and hard negatives).
2. Add reviewed answer and citation labels, and an optional bounded judge-model check.
3. Add regression thresholds that fail the daily run, and trend views in MLflow.
