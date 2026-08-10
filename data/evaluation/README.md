# Evaluation datasets

These files are versioned human-reviewed labels, not automatically generated
search examples. A retrieval case should contain:

```json
{
  "case_id": "tax-retrieval-001",
  "query": "...",
  "relevant_document_numbers": ["..."],
  "relevant_articles": ["..."],
  "answerable": true,
  "category": "direct_lookup",
  "difficulty": "medium"
}
```

Only `case_id`, `query`, and `relevant_document_numbers` are currently required
by the runner. Article labels and the other fields are the expansion path for
article-level and answer-quality evaluation. Record the official source and
reviewer notes in the dataset change when adding or changing a label.

Before treating a score as a ranking result, inspect the report's
`evaluation_status`, `quality_gate`, and `corpus_snapshot`. A run with no
embedded expected documents is `not_evaluable`, even when the search returns
other documents.

Run the default multi-K retrieval evaluation with:

```powershell
python scripts/evaluate_tax_retrieval.py
```

Use `--k 5` for the legacy single-K behavior.

Evaluate a retrieval baseline explicitly with `--mode keyword`, `--mode
semantic`, or `--mode hybrid`. Run the same dataset and corpus snapshot for
each mode when comparing baselines.
