# Retrieval experiments

The record of retrieval experiments on the gold set, in the order they were done. Later
sections do not rewrite earlier ones. For where things stand now, read
[evaluation-status.md](evaluation-status.md).

| Date | Experiment | Sections |
| --- | --- | --- |
| 31/10/2026 | Issue-guided retrieval | [Question](#question) to [First results](#first-results-31102026) |
| 04/11/2026 | Following one legal reference | [Upper limit](#following-one-legal-reference-upper-limit-04112026) |
| 04/11/2026 | Removing documents that had ended | [Plan](#removing-documents-that-had-ended-experiment-plan-04112026), [results](#removing-documents-that-had-ended-results-04112026) |
| 04/11/2026 | The ministry's expiry dates | [Plan](#adding-the-ministrys-expiry-dates-experiment-plan-04112026), [results](#adding-the-ministrys-expiry-dates-results-04112026) |
| 05/11/2026 | Repaired text and two circulars | [Plan](#plan-repaired-text-and-the-two-circulars-05112026), [results](#repaired-text-and-the-two-circulars-results-05112026) |
| 05/11/2026 | Why A4 and L2 stay unfound | [Diagnosis](#why-a4-and-l2-stay-unfound-05112026) |

The issue-guided plan below was written before any result was seen, so the comparison
cannot be tuned to the gold set. Changes after the first run are recorded at the end with
their reason.

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

## Following one legal reference: upper limit (04/11/2026)

Could following one explicit reference from the retrieved passages recover what they miss?
`scripts/measure_reference_reachability.py` parses references in the top K passages
(`taxlens/retrieval/references.py`) and asks whether one points at a missed essential
provision held in the corpus. Nothing is re-ranked, so this bounds a method and does not
measure one. Same inputs as the first results; reports are
`reachability-*-asof-k10.json`.

| Seed passages (K = 10) | Hybrid, of 23 missed | Issue-guided, of 20 missed |
| --- | --- | --- |
| All | 0 | 1 (document level) |
| Issued from 2020 on (exploratory) | 3 (1 clause, 2 document level) | 3 (clause level) |

Hand reading of the matches: Decree 360 Art 3(4) -> Special Consumption Tax Law Art 2(1)
(A1) and Decree 181 Art 4 -> VAT Law Art 5 (A6) are correct. Decree 181 Art 19 -> Art 4(1)
(A2) is correct, but that clause has no passage because OCR lost its numbers. Decree 359
Art 1 mentions Decree 181 only at document level (A2).

About 80% of the top passages come from documents issued before 2020, and those rarely
cite the provisions a 2025-2026 case needs. Even without them most misses are reached by
no reference, so one hop looks like a small supplement to ranking, not a fix for it.
Removing replaced documents should be tested first.

Limits: 12 cases, one parser, OCR text. The 2020 cutoff was chosen after seeing the
results and is not a tested filter. It was computed from a saved top-50 list, so fewer
than K passages may remain for a case. The runs were made from a laptop against the frozen
corpus (checked with `freeze_corpus.py --check`), not in the API image; the top five
documents of every saved report reproduced.

## Removing documents that had ended: experiment plan (04/11/2026)

Written before any retrieval run with the filter. The extraction was inspected only for
what it removes, never for how a method scores.

**Question.** Does leaving out documents that had ended by a case's date retrieve more of
its essential provisions within the same budget?

**Why not the recorded status.** The corpus holds no expired document and marks
`219/2013/TT-BTC` as `EFFECTIVE`, while most gold documents are `DISCOVERED`.

**Method** (`taxlens/retrieval/repeals.py`, `scripts/extract_repeals.py`). Stored once in
`data/evaluation/repeals/corpus-v1.json`, without using the gold set:

- `explicit`: a document says another ends entirely (`hết hiệu lực`, `bãi bỏ`, `thay
  thế`). Statements about a part of a document are ignored.
- `guidance`: a title says the document guides or details one that ended, by number or by
  the law of that name in force when it was issued.
- `amendment`: a title says the document amends one that ended.

A document ends on its repealer's date, and is left out only for cases on or after that
date. `guidance` and `amendment` are inferences that a legal expert should validate.

**Runs**, all on `corpus-v1`, `gold-v1.0 --verified-only`, `--as-of case`, K = 5, 10, 20:

| Run | Baseline |
| --- | --- |
| `hybrid`, all rules (`hybrid-asof-repeals.json`) | `hybrid-asof.json` |
| `issue-guided`, all rules (`issue-guided-asof-repeals.json`) | `issue-guided-asof.json` |
| `hybrid`, `explicit` only (`hybrid-asof-repeals-explicit.json`) | `hybrid-asof.json` |
| `issue-guided`, `explicit` only (`issue-guided-asof-repeals-explicit.json`) | `issue-guided-asof.json` |

**Measures.** Primary: `essential_in_corpus_full_coverage_rate`, then
`mean_essential_in_corpus_recall_at_k`, with paired wins and losses and an exact sign test
from `scripts/compare_retrieval_runs.py`. No threshold is claimed with 12 cases. Also
reported: gold provisions the filter removes (a filter error if any), and the one-hop
check at K = 10 on the filtered runs.

**Known limits.** Documents that end without any statement in the corpus stay in (for
example `47/2011/TT-BTC`). OCR can hide a statement. Amended document numbers written in
more than one way are treated separately.

## Removing documents that had ended: results (04/11/2026)

321 of 2,026 documents are listed as ended (239 `explicit`, 43 `guidance`, 39
`amendment`). No essential gold provision's document had ended by its case's date.
Reports: `data/evaluation/runs/*-repeals*.json`.

Essential recall over provisions held in the corpus (full coverage in brackets):

| Run | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| hybrid | 0.09 (0) | 0.14 (0) | 0.20 (0) |
| hybrid, all rules | 0.14 (0) | 0.25 (0.09) | 0.34 (0.18) |
| hybrid, `explicit` only | 0.09 (0) | 0.14 (0) | 0.20 (0) |
| issue-guided | 0.16 (0) | 0.23 (0) | 0.23 (0) |
| issue-guided, all rules | 0.25 (0) | 0.27 (0) | 0.27 (0) |
| issue-guided, `explicit` only | 0.16 (0) | 0.23 (0) | 0.23 (0) |

Paired against the same method without the filter, all rules:

| Method | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| hybrid (wins, losses, ties; p) | 1, 0, 11; 1.0 | 3, 0, 9; 0.25 | 3, 0, 9; 0.25 |
| issue-guided | 2, 0, 10; 0.5 | 1, 0, 11; 1.0 | 1, 0, 11; 1.0 |

The direction favours the filter and it lost no case, but 12 cases cannot show a
difference. These are the first non-zero full-coverage results (hybrid: A8 at K = 10, A8
and L3 at K = 20).

`explicit` alone changed the top ten documents in 7 of 12 cases and found no further
provision. All of the gain comes from `guidance` and `amendment`, the two inferred rules
that have not been validated by a legal expert. Results depend on them.

Missed at K = 10 with the filter, hybrid 24 and issue-guided 23: 13 and 12 not in the top
200, 6 and 6 ranked below K, 4 not in corpus, 1 no passage. One hop from filtered passages
reaches 2 of 20 for hybrid (A1 at clause level, A2 at document level) and 1 of 19 for
issue-guided (A2 at document level), so it remains a small supplement.

Old documents with no statement in the corpus now lead many rankings (`194/2010/TT-BTC`,
`06/2000/TT-TCHQ`, `18/2001/TT-BTC`, `54/2003/TTLT-BTC-BTM`, `122/2000/TT-BTC`). Most
misses are still not found in the top 200, which suggests the next limit is matching the
question to the laws and decrees, not stale documents alone.

## Adding the ministry's expiry dates: experiment plan (04/11/2026)

Written before any run. The repeal filter gets all its gain from two inferred rules, and
the ministry lists 120 corpus documents as expired that the filter keeps.

**Method.** `scripts/add_ministry_expiry.py` adds a `ministry` rule to a new file,
`data/evaluation/repeals/corpus-v1-ministry.json`: a corpus document the ministry marks
`Hết hiệu lực`, with a real expiry date (placeholders from year 2900 are ignored). Where a
document is already listed, the earlier date stands. The ministry's status is as of
04/11/2026, and only its dates decide whether a case is affected.

**Runs**, same inputs as before, K = 5, 10, 20:

| Run | Rules | Baseline |
| --- | --- | --- |
| `hybrid-asof-ministry-all`, `issue-guided-asof-ministry-all` | all four | the same method with the three earlier rules |
| `hybrid-asof-ministry-explicit`, `issue-guided-asof-ministry-explicit` | `explicit`, `ministry` | the same method with no filter |

The second pair asks whether stated and official dates can replace the unvalidated
inferences. Measures as before; gold provisions removed are reported as filter errors.

Correction after the first runs: a document already listed by an inference kept that label
even when the ministry confirmed it, so `explicit` + `ministry` wrongly kept
`219/2013/TT-BTC` and seven others. Such documents now take the `ministry` label, and that
pair was run again. The result of all four rules does not depend on the label.

## Adding the ministry's expiry dates: results (04/11/2026)

The ministry's dates list 119 more documents as ended and confirm 8 inferred ones, among
them `219/2013/TT-BTC`. No gold provision's document had ended by its case's date.

Essential recall over provisions held in the corpus (full coverage in brackets):

| Filter | Hybrid, K = 5 | K = 10 | K = 20 | Issue-guided, K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- | --- | --- | --- |
| None | 0.09 (0) | 0.14 (0) | 0.20 (0) | 0.16 (0) | 0.23 (0) | 0.23 (0) |
| `explicit` + `ministry` | 0.09 (0) | 0.20 (0) | 0.25 (0.09) | 0.20 (0) | 0.27 (0) | 0.27 (0) |
| `explicit` + inferred | 0.14 (0) | 0.25 (0.09) | 0.34 (0.18) | 0.25 (0) | 0.27 (0) | 0.27 (0) |
| All four | 0.14 (0) | 0.25 (0.09) | 0.34 (0.18) | 0.25 (0) | 0.27 (0) | 0.27 (0) |

Against no filter, `explicit` + `ministry` wins 2, loses 0 at K = 10 for hybrid (p = 0.5)
and wins 1, loses 0 for issue-guided (p = 1.0). So the ministry's record, which needs no
inference, reproduces part of the gain and all of issue-guided's at K = 10 and 20. The
rest still depends on `guidance` and `amendment`, such as `130/2016/TT-BTC` and
`26/2015/TT-BTC`, which the ministry lists as in force.

All four rules changed the top ten documents in 4 of 12 cases and found no further
provision, so the 119 extra documents add nothing on these 12 cases.

## Plan: repaired text and the two circulars (05/11/2026)

Written before any run. Two questions, kept apart by adding one change at a time:

1. Do split syllables lower retrieval? `corpus-v1.1` is `corpus-v1` with the 8 affected PDFs
   read again. Dry run on the stored files: 6 fall to 0 per 1,000 words, `254/2013/TT-BTC`
   to 3.1, and `191/2010/TT-BTC` only to 31.9, so one stays broken.
2. What do Circulars 80/2021 and 25/2018 add? `corpus-v1.2` is `corpus-v1.1` plus both.

Runs, each with `gold-v1.0 --verified-only` and `--as-of case`:

| Corpus | Runs | Compared with |
| --- | --- | --- |
| `corpus-v1.1` | hybrid, issue-guided | `corpus-v1` |
| `corpus-v1.2` | hybrid, issue-guided | `corpus-v1.1` |
| `corpus-v1.2` | both with the `explicit` + inferred filter | no filter on `corpus-v1.2`; the same filter on `corpus-v1` |

Measures: essential recall at K = 5, 10, 20, full coverage, and paired wins and losses. Adding
the circulars raises the number of provisions held in the corpus, which can lower mean recall
by itself, so A4, A7, and L2 are reported case by case, and recall is also given over the
provisions `corpus-v1` already held. The repeal list is the `corpus-v1` one and does not list
either circular. With 12 cases, a small change is not evidence either way.

`corpus-v1` keeps its manifest and reports. Reprocessing replaces the 8 PDFs' passages in the
database, so a run against `corpus-v1` now stops at its corpus check; the old passages and
embeddings are saved in `data/local/backups/corpus-v1-8pdfs.json` (not committed). The
circulars are the text as first published.

## Repaired text and the two circulars: results (05/11/2026)

Essential recall over provisions held in the corpus (full coverage in brackets where it is not 0):

| Method | Corpus | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- | --- |
| Hybrid | `corpus-v1` | 0.09 | 0.14 | 0.20 |
| | `corpus-v1.1` | 0.09 | 0.14 | 0.20 |
| | `corpus-v1.2` | 0.11 | 0.15 | 0.22 |
| Hybrid + filter | `corpus-v1` | 0.14 | 0.25 (0.09) | 0.34 (0.18) |
| | `corpus-v1.2` | 0.13 | 0.26 (0.08) | 0.34 (0.17) |
| Issue-guided | `corpus-v1` | 0.16 | 0.23 | 0.23 |
| | `corpus-v1.1` | 0.16 | 0.23 | 0.25 |
| | `corpus-v1.2` | 0.15 | 0.21 | 0.26 |
| Issue-guided + filter | `corpus-v1` | 0.25 | 0.27 | 0.27 |
| | `corpus-v1.2` | 0.26 | 0.28 | 0.30 |

`corpus-v1` scores 11 cases and `corpus-v1.2` 12, because L2 now has a held provision and A4
and A7 have more, so the two rows are not on the same denominator.

Split syllables: repairing them changed almost nothing. Of the 11 essential provisions in the
repaired laws, 10 keep the same rank in both methods. The one change is `84/2025/TT-BNNMT` Art
20(1)(c) in A2, which issue-guided now finds at rank 19. So split syllables were not why these
provisions were missed, and the idea is not supported. The repair stays because it costs
nothing and gives correct text to answer from.

The circulars, by case (no filter, then with filter):

| Case | Provision | Hybrid | Issue-guided |
| --- | --- | --- | --- |
| A7 | 25/2018 Art 2 | rank 4, then 6 | rank 15, then 2 |
| L2 | 25/2018 Art 2 | not found, not found | not found, not found |
| A4 | 80/2021 Art 40(3), Art 21 | not found, not found | not found, not found |

Over provisions `corpus-v1` already held, adding them made no difference at K = 5 or 20 without
the filter. Hybrid at K = 10 gained A5 and lost A3, so about 1,000 new passages moved rankings
without a net effect. For A4, hybrid ranks the document 5th, but not the cited articles.

On `corpus-v1.2` the filter against no filter wins 3, loses 0 at K = 10 for hybrid (p = 0.25)
and wins 2, loses 0 for issue-guided (p = 0.5). It still removes no gold document.
`compare_retrieval_runs.py` refuses pairs from different corpora, so wins and losses across
corpora were counted on the provisions both runs hold.

The result: coverage was only part of the problem. Having the document made one of three cases
retrievable, and the database now holds `corpus-v1.2` (fingerprint `7df84879`). Runs against
`corpus-v1` now stop at the corpus check.

## Why A4 and L2 stay unfound (05/11/2026)

Exploratory and read-only, on `corpus-v1.2`, `--as-of case`. It was not planned in advance,
and it uses the same 12 cases that showed the problem, so treat it as a strong lead that needs
a planned rerun, not as a result of record.

Ranks of the gold passages in each list before fusion (exact vector search, no filter). Hybrid
search takes the top 50 of each list:

| Case | Passage | Keyword | Vector |
| --- | --- | --- | --- |
| A7, found | 25/2018 Art 2, two passages | 185, 1,041 | 1, 3 |
| L2, not found | 25/2018 Art 2, two passages | 91, 117 | 17, 22 |
| A4, not found | 80/2021 Art 40(3) | 2,159 | 48 |
| A4, not found | 80/2021 Art 21, three passages | not matched | below 5,000 |

**The main cause is the keyword term limit.** `MAX_KEYWORD_TERMS = 12` keeps a question's first
12 terms after stopwords. Every scored question has more: 18 to 40. For long natural questions
the kept terms are mostly the opening (`Tháng`, `công`, `ty`, `tôi`, `đã`), and the legal
content is cut: A4 loses `khẩu`, `khách`, `trả`, `lại`, and L2 loses `GTGT`, `hoàn`, `300`,
`triệu`. The keyword list is then noise, and fusion ranks that noise above a passage found by
vector search alone. Keyword search alone scored 0 at every K in every run, which should have
prompted this check much earlier.

Raising the limit to 40, which removes it for all 12 questions, and changing nothing else
(hybrid on `corpus-v1.2`, no filter):

| Limit | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| 12 | 0.11 (0) | 0.15 (0) | 0.22 (0) |
| 40 | 0.30 (0.08) | 0.41 (0.17) | 0.45 (0.25) |

Paired: 5 wins, 1 loss at K = 5 (p = 0.22; A7 falls from rank 4 to 6), 6 wins, 0 losses at K =
10 (p = 0.03), and 5 wins, 0 losses at K = 20 (p = 0.06). L2's keyword rank goes from 91 to 1
and it reaches rank 5 after fusion. Reports: `hybrid-asof-v1.2-terms40.json`, with the
single-list runs `keyword-asof-v1.2.json` and `semantic-asof-v1.2.json`. The report's code
version does not show the changed limit, which was set at run time.

Every earlier figure in this document was measured under the limit of 12. Issue-guided search
and the filters have not been run without it, so their gains may be larger or smaller.

**A4 is not fixed by this,** for separate reasons:

- Art 40(3) still ranks 162 by keyword. Its wording (`người bán trả lại`) differs from the
  question's (`khách hàng nước ngoài trả lại`), and many old passages match common terms.
- Art 21 concerns late-payment interest, which the question never mentions. No single search
  can reach it; it needs a legal step from the recovery of the refund to its interest.
- At the limit of 12, 20 of the top 50 keyword passages for A4 are forms and tax returns,
  including `80/2021` Art 89's appendix. At 40 terms that falls to 3.

Other observations: vector scores are close together (for L2, 0.93 at the top and 0.91 at rank
50), so small differences decide the top ten. L2's rule also appears in Decree 146/2017 Art 1,
a supporting provision for that case. `89/2026/TT-BTC` repeats A4's rule at Art 54, but it was
issued on 30/06/2026, after the case date.

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
