# Evaluation datasets

These files are versioned labels, not automatically generated search examples.
`tax_article_retrieval.json` is the default scheduled dataset: 18 answerable
Vietnamese questions (four typed without diacritics) labelled with the document
and article that answers them, plus two out-of-corpus questions that are skipped
by the ranking metrics. Its labels were checked against the article headings of
the five curated tax documents; see `docs/retrieval.md` for measured results.
`tax_retrieval_current.json` (eight cases) and `tax_retrieval.json` (four cases) are
older document-level smoke sets, kept for regression; they are not reviewed benchmarks.
`qa.json` holds five questions for `scripts/evaluate_qa.py`. The labels were made when the
corpus held a handful of documents; relabelling against the full corpus is the next step
(`docs/evaluation.md`).

A retrieval case should contain:

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
label-provenance notes in the dataset change when adding or changing a label.

Before treating a score as a ranking result, inspect the report's
`evaluation_status`, `quality_gate`, and `corpus_snapshot`. A run with no
embedded expected documents is `not_evaluable`, even when the search returns
other documents.

Run the default evaluation with:

```powershell
python scripts/evaluate_tax_retrieval.py
```

Evaluate a retrieval baseline explicitly with `--mode keyword`, `--mode
semantic`, or `--mode hybrid`. Run the same dataset and corpus snapshot for
each mode when comparing baselines.
