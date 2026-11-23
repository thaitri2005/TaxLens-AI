# Retrieval and cited answers

How documents become passages, how passages are found, and how an answer is given and cited. Every step
is deterministic except the model call, and thresholds are settings in `src/taxlens/config.py`.

```text
File → text (Word/RTF, PDF layer, or OCR) → article and clause passages → keyword and vector indexes
Question → keyword + semantic → reciprocal rank fusion → evidence gate → model → citation checks
```

## 1. Text extraction

- **Word, RTF, DOCX** are read directly (`document_processing/formats.py`). The format comes from the
  content, since files named `.doc` or `.rtf` can be RTF or PDF. TCVN3 and Windows Vietnamese text is
  converted to Unicode (`legacy_text.py`), by line and, in mixed-font lines, by word.
- **PDF pages** keep their text layer if usable: at least 40 non-space characters and 20% letters. A
  layer with under 5% accented letters, cut syllables, or control characters is distrusted; that page is
  OCR'd and the result kept only if it reads clearly more Vietnamese. A PDF layer is converted from
  TCVN3 only if most of it is TCVN3. OCR text is never converted, as its noise can look like TCVN3.
- **OCR:** Tesseract `vie`, 300 DPI, mode 6, grayscale, `OMP_THREAD_LIMIT=1`. A page over 240 s is left
  empty and recorded as `OCR_PAGES_FAILED`.
- **Split syllables:** above 5 cuts per 1,000 words, `pypdfium2`'s text replaces `pypdf`'s when cleaner.
- Text is normalized to NFC, with pages joined by a form feed so passages keep page numbers.

Later stages tolerate OCR errors: lost accents, stray punctuation before headings.

## 2. Chunking (`document_processing/process.py`)

Follows *Điều* (article) → *khoản* (clause). `CHUNKER_VERSION` is 4, recorded in the job stage as
`CHUNKED:v4`. A changed version re-chunks from stored text with no OCR, and passages whose text did not
change keep their embeddings.

1. **Article headings:** lines starting `Điều N.` or `Điều N:`, with OCR spellings and up to six noise
   characters. Numbers must increase. Cross-references, wrapped lines, and quoted headings (amended text
   in an amending decree) are not articles.
2. **Preamble:** kept as its own passage.
3. **Clauses:** an article over 1,500 characters splits at numbered clauses. Each passage records article,
   clause, heading, and pages.
4. **Size cap:** anything over 1,500 characters splits at line, then word.
5. **No articles:** older documents split by section (`PHẦN A`, `Chương II`, Roman numerals).
6. **After the signature:** text is labelled appendix rather than filed under the last article.

The number in the header (`Số: 301/2026/NĐ-CP`) is compared with the stored number, and a difference is
recorded as `DOCUMENT_NUMBER_MISMATCH`. Most flags are OCR misreads; real errors are fixed with
`correct_document_numbers.py`.

## 3. Keyword search (`retrieval/search.py`)

Two generated `tsvector` columns, accented and unaccented, both GIN-indexed.

1. The query is split into terms, dropping question and function words but keeping `không`. At most 64
   terms (`MAX_KEYWORD_TERMS`).
2. Passages matching **any** unaccented term are candidates.
3. Score: distinct terms matched, plus 0.5 for each that also matches with accents (so `thuế` beats
   `thuê`), plus a tie-breaker below 1 calculated only for passages that can still reach the top.

Term matches are counted from the GIN indexes, one scan per term. The query runs without a parallel worker
(the database has one vCore): a 29-term question takes about 2.4 s instead of 3.4 s, with identical results.

## 4. Semantic search and fusion

`intfloat/multilingual-e5-small` (pinned, CPU, in the API image), with `passage:` and `query:` prefixes.
Hybrid takes 50 candidates from each method and combines them with reciprocal rank fusion (k = 60). If
the model cannot load, search falls back to keyword.

- Vector search is exact (`distance + 0`). There is no HNSW index, since it could silently shorten the
  candidate list.
- Filters (ended documents, the period, a named document, chips) are first resolved to the versions they
  keep, and both searches run against that list. Joined into the scans, they led PostgreSQL to plans 3-5
  times slower.
- A question naming exactly one document number is restricted to that document.
- A question naming no document number is answered for a period: the dates it names ("Tháng 6/2023",
  "quý II/2025", "năm 2024", but not a document's issue date), or today, Vietnam time
  (`intelligence/planning.py`). Documents whose end is confirmed by the period's start are left out
  ([ended documents](#ended-documents)), and versions taking effect after its end; the model is told the
  period. A question that names documents keeps them, since it may be about an old one.
- Answers search 20 passages and keep the first 5 with an article, clause, section, or page, so old
  documents without articles cannot fill every place. Passages of documents that may have ended by the
  period's start (an inferred ending) come after the others and only fill places left over.
- Passages with four or more blank-field runs count as forms, and are left out unless the question asks
  for one (`mẫu số`, `biểu mẫu`, `mẫu biểu`, `mẫu đơn`, `tờ khai`).
- The embedding model reads 512 tokens: 0.5% of article passages and 18% of other text exceed it, losing
  5-6% of their length from the vector. Keyword search sees all of it.

## 5. Evidence gate (`intelligence/evidence.py`)

Before any model call, the selected passages (5 by default):

| Check | Outcome |
| --- | --- |
| No passages | `NO_EVIDENCE` |
| Best similarity below `QA_MIN_SEMANTIC_SCORE` (0.80) | `LOW_RELEVANCE`, no model call |
| No article, clause, or page locator | Dropped and noted |
| Superseded or expired while current ones exist | Dropped and noted |
| Only superseded or expired | `INACTIVE_ONLY` |
| Versions with different known statuses | `CONFLICTING_VERSIONS` |
| Otherwise | `SUFFICIENT`; `DISCOVERED` status is noted |

Recorded status rarely helps, since most portal documents are `DISCOVERED`; ended documents are handled
before the gate, by their recorded ending. Each cited document that has or may have ended, or is recorded
to end later, gets a note among the answer's uncertainties.

### Ended documents

`legal_documents.ended_on`, `end_basis`, and `ended_by` hold one ending per document, loaded from a
committed list (`data/evaluation/repeals/corpus-v2.1-ministry.json`) by `apply_document_endings.py`. The
bases are the rules of `retrieval/repeals.py`, and the date is compared with today on every request, so a
future ending takes effect by itself.

| Basis | Meaning | Answers | Shown |
| --- | --- | --- | --- |
| `explicit` | A document in the corpus says this one ends; `ended_by` names it | Left out | "Ended", with the document |
| `ministry` | The Ministry of Finance records it as expired | Left out | "Ended", Ministry of Finance record |
| `guidance` | It guides a document that ended (`ended_by`) | Kept, noted | "May have ended" |
| `amendment` | It amends a document that ended (`ended_by`) | Kept, noted | "May have ended" |

Only the first two act, as no legal expert has validated the inferred rules. On `corpus-v2.1`, as of
23/11/2026, that leaves out 729 documents (3 more end later) and flags 127; answers use a flagged
document only when too few others are found. An explicit statement may end a run of documents ("thay
thế các Thông tư số X ngày …, Thông tư số Y … và Thông tư số Z"): the run continues through items
separated only by a date, an issuer, and a comma or "và", so a title or a part stops it. In evaluation it gives recall
0.31, 0.42, 0.45 at K = 5, 10, 20, against 0.10, 0.30, 0.41 without it ([status](evaluation-status.md#results)). Search pages show the same tags but leave nothing out, since
looking up an old document is a normal use.

## 6. Answers (`intelligence/qa.py`)

A LangGraph graph: plan → retrieve → assess → generate → validate. The model gets numbered passages with
document, status, article, clause, pages, and any ending note, and the period the question concerns,
through the provider-neutral `ChatProvider`. It is told never to call a document in force after its
ending date, and to prefer passages without an ending and the later of two documents on one matter. It must answer
in the question's language, return `answerable: false` if the passages do not answer it, and give at
most five confirmed facts, an answer of about 250 words, and one to four practical steps that add no new
rules.

Checks: `answerable: false` becomes `INSUFFICIENT_EVIDENCE`; citation numbers must exist; at least 50% of
a fact's words (`QA_MIN_FACT_SUPPORT`, without accents) must occur in its cited passages, or it is
removed and reported. Citations carry verbatim excerpts. Unparseable output is `INVALID_MODEL_OUTPUT`,
and provider failures are `PROVIDER_UNAVAILABLE`.

Grounding is lexical, so a misleading fact using the passage's words would pass.

Every question is logged in `question_logs` with its status, answer, cited documents, and time, and the
asker can rate the answer 👍/👎 with a comment ([architecture](architecture.md#logging)).

## Evaluation

Results are in [evaluation-status.md](evaluation-status.md), and past runs in
[retrieval-experiments.md](retrieval-experiments.md).

| File | Contents |
| --- | --- |
| `gold_set_v1.csv` | The benchmark: taxpayer situations from tax-authority letters, labelled to the clause ([guideline](annotation-guideline.md)). Tag `gold-v1.0` |
| `tax_article_retrieval.json` | Daily regression set: 18 short questions on five documents |
| `tax_retrieval_current.json`, `tax_retrieval.json` | Older smoke sets |
| `qa.json` | Five questions for `evaluate_qa.py` |
| `issues/gold_set_v1.json` | Stored issue decompositions |
| `gold_set_v1_drafts.csv` | 18 drafted cases waiting for an annotator; not scored ([guideline](annotation-guideline.md)) |
| `repeals/corpus-v2.1-ministry.json` | Current list of ended documents |

Run a frozen comparison:

```powershell
python scripts/freeze_corpus.py --check data/evaluation/corpus/corpus-v2.1.json
python scripts/evaluate_tax_retrieval.py --dataset data/evaluation/gold_set_v1.csv --verified-only --corpus-manifest data/evaluation/corpus/corpus-v2.1.json --as-of case --ks 5 10 20 --mode hybrid --repeals data/evaluation/repeals/corpus-v2.1-ministry.json --output data/evaluation/runs/NAME.json
python scripts/compare_retrieval_runs.py data/evaluation/runs/A.json data/evaluation/runs/B.json
```

Modes: `keyword`, `semantic`, `hybrid`, `issue-guided` (with `--issues`). `--corpus-manifest` stops if the
corpus changed. Reports record the corpus, dataset hash, model, filters, and commit, so commit code first.

**Measures.** `essential_full_coverage_rate` (all essential provisions in the top K) is the headline.
`mean_essential_recall_at_k` is the share found. `essential_in_corpus_*` leaves out documents the corpus
lacks. `essential_provision_ranks` lists first ranks per provision. Only E provisions score; S are
reported. `--verified-only` skips uncertain and unverified cases. `--as-of case` drops versions that take
effect after the case date (or filing date), using the issue date when no effective date is recorded.

**Parsing gold provisions** (`evaluation/gold_set.py`): the cited provision comes before the first comma
or parenthesis. An amended provision and its amendment count once. Short numbers complete from the corpus.
Unreadable items go to `unparsed_provisions`. A passage with no clause number holds the whole article.

`--reranker MODEL` reorders the top `--rerank-candidates` (100) hybrid passages with a cross-encoder
(`retrieval/reranking.py`); `--rerank-fuse` fuses its order with the hybrid one, and `--rerank-cache FILE`
keeps scores so a model is scored once. None is used by the site ([tried](retrieval-experiments.md#retrieval)).

**`grade_answers.py`** answers each gold question as the site does and has a judge model from another family
(`Qwen/Qwen3-235B-A22B-Instruct-2507`) grade it against the gold answer: correct, partly, wrong, or
refused. Read every reason and record disagreements in the report; `--regrade` fills grades the judge's
rate limit dropped. About $0.05 a run. Latest: 8 correct, 2 wrong, 5 refused of 15 ([answers](evaluation-status.md#answers)).

**`export_question_log.py`** writes rated and refused questions from the site to a CSV, as gold-case
candidates.

**`evaluate_qa.py`** reports faithfulness, answer relevancy, context precision, and citation completeness.
All are lexical. It needs `HF_TOKEN` and prints only at the end. MLflow logging is optional
(`MLFLOW_ENABLED=true`, `docker compose --profile llmops up -d mlflow`).

When adding a label, record its official source and how it was checked.
