# Issue-guided retrieval: experiment plan

Written before any result was seen, so the comparison cannot be tuned to the gold set.
Changes after the first run are recorded at the end with their reason.

## Question

Does searching once per legal issue retrieve more of a case's **essential provisions**
than one hybrid search for the whole question, with the same number of passages?

A taxpayer's question usually needs several provisions that share few words with it: the
rate, the exception that overrides it, a definition in another document, the procedure.
One query ranks the provision closest to the question's wording and pushes the others
out of the budget.

## Methods

| Run | What it does |
| --- | --- |
| `keyword`, `semantic`, `hybrid` | The existing TaxLens search ([retrieval.md](retrieval.md)), one query: the question. |
| `hybrid --as-of case` | The same, leaving out documents that take effect after the case date. |
| `issue-guided --as-of case` | The method: hybrid search for the question and for each stored issue, interleaved. |

**Issue decomposition** (`taxlens/retrieval/issues.py`, prompt `issues-v2`): the answer
model (`HF_CHAT_MODEL`, Qwen3-4B-Instruct, temperature 0) lists up to four legal issues of
the situation and the case date, each as a short search phrase in statutory wording.
Phrases may not contain document, article, or clause numbers, so the method is credited
for finding provisions, not the model for remembering them. Decompositions are made once
(`scripts/decompose_issues.py`) and stored in `data/evaluation/issues/gold_set_v1.json`;
runs read that file and call no model.

**Merging under the same budget:** the question's ranking and each issue's ranking are
interleaved, one passage from each in turn, the question first, skipping passages already
taken. The first K passages are the method's answer at budget K, as the first K are the
baseline's. Both see the same corpus, filters, and search code.

## Frozen inputs

- Corpus: `data/evaluation/corpus/corpus-v1.json` (`--corpus-manifest` refuses a drifted
  corpus).
- Gold set: `gold_set_v1.csv` at tag `gold-v1.0`, `--verified-only`.
- Decompositions: the stored file; its hash is in each report.

## Measures

At K = 5, 10, 20 passages:

1. **Primary:** `essential_in_corpus_full_coverage_rate`, the share of cases whose every
   essential provision held in the corpus is in the top K.
2. `mean_essential_in_corpus_recall_at_k`, and the raw versions that count corpus gaps as
   misses.
3. Supporting recall, reported only.

Per case: win (method covers an essential provision the baseline misses at K, and misses
none it covers), loss, or tie. With about 25 cases a significance test has little power,
so the result is stated as paired wins and losses with an exact sign test, plus the
per-case table; no threshold is claimed. `scripts/compare_retrieval_runs.py <baseline>
<method>` computes both from the saved reports and refuses reports made on different
corpora, datasets, or date filters.

## Error analysis

Every essential provision missed at K = 10 gets one cause: not in corpus; wrong version
by date; passage truncated by the 512-token embedding limit; issue not identified by the
decomposition; identified but ranked below K.

## Known limitations

- Only one decomposition per question; model variation is not measured.
- The 512-token embedding truncation affects both methods equally.
- Effective dates are per document, and repealed law is not removed by `--as-of`.

## First results (31/10/2026)

`corpus-v1` (fingerprint `317f5a0d`), `gold-v1.0 --verified-only`: 12 scored cases (9
letters, L2–L4); 4 essential provisions are corpus gaps (Circulars 80/2021 and
25/2018, in no official source we collect). Reports: `data/evaluation/runs/`.

Essential recall over provisions held in the corpus:

| Run | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| keyword | 0.00 | 0.00 | 0.00 |
| semantic | 0.09 | 0.11 | 0.11 |
| hybrid | 0.09 | 0.09 | 0.20 |
| hybrid, `--as-of case` | 0.09 | 0.14 | 0.20 |
| issue-guided | 0.00 | 0.20 | 0.23 |
| issue-guided, `--as-of case` | 0.16 | 0.23 | 0.23 |

Full coverage is 0 for every run at every K: no case had all its essential provisions
retrieved.

Paired, both with `--as-of case`: issue-guided wins 2, loses 0, ties 10 at K = 5 and
K = 10 (sign test p = 0.5); wins 2, loses 1 at K = 20. The direction favours the
method, but 12 cases cannot show a difference.

Error analysis at K = 10 (`diagnosis-*-k10.json`), 27 missed provisions for hybrid and
24 for issue-guided:

| Cause | Hybrid | Issue-guided |
| --- | --- | --- |
| Not in the top 200 | 13 | 12 |
| Ranked below K (in the top 200) | 9 | 7 |
| Not in corpus | 4 | 4 |
| No passage (Decree 181 Art 4(1): OCR lost the clause numbers) | 1 | 1 |
| Excluded by date | 0 | 0 |
| Truncated by the 512-token limit | 0 | 0 |

The misses are ranking failures, not corpus or chunking failures: the passages exist
and hold the right text. In 11 of 12 cases an older VAT circular (219/2013, 26/2015,
130/2016 …) is among the top three documents, and in 8 the top document predates 2020.
Those circulars no longer apply from 1/7/2025, but nothing in the corpus says when a
document stopped applying, so `--as-of` cannot remove them. The laws themselves rank
worst: VAT Law 48/2024 and Tax Administration Law 38/2019 provisions are missed in
almost every case that needs them.

What this suggests, to test next: (1) use the ministry's legal status and replacement
links to drop replaced documents before a case date; (2) rank laws and decrees above
the circulars that implement them when both match; (3) more cases, since 12 cannot
separate the methods.

## Changes

- `issues-v1` → `issues-v2` (before any retrieval run): v1 wrote whole questions that
  repeated the situation's amounts and dates, so keyword search kept only their first
  terms and the issues barely differed from the question.
- `--as-of` falls back to the issue date when a version has no effective date (after the
  first runs, before any comparison was made): portal documents record no effective
  date, so cases dated 2023 and 2024 still retrieved the 2024 VAT Law and Decree
  181/2025. The filter is shared by both methods; every run was repeated.
- `--as-of case` uses the later of `as_of_date` and `filing_date` (found by the error
  analysis, before the comparison was reported): A7's refund was filed on 15/09/2025,
  and the law in force then is what the letter applies, but the filter dropped it as
  later than the 2024 facts. Only A7 has a filing date.
