# Oracle issue experiment: plan

Written 24/11/2026, before any oracle query was drafted or run. Suggested by Prof. Thanh: name the
missing legal issues of the hardest cases by hand, and test whether searches for them recover the
essential provisions. This separates two explanations of the misses:

- **Reasoning:** search works once the right issue is named; the system fails to name it. Then a step
  that works out the governing law (to-do item 16) is worth building, and this experiment is its ceiling.
- **Retrieval:** even the named issue does not find the provision (wording, OCR, chunking). Then item 16
  would not help, and retrieval itself needs work.

## Fixed inputs

- Corpus `corpus-v2.1` (fingerprint `07175db6`), gold set at `d568800` (34 cases), endings list
  `corpus-v2.1-ministry.json` with the live rules (`explicit`, `ministry`), each case's `as_of_date`.
- Search: the live hybrid search (`hybrid_search_chunks`), unchanged.
- Baseline: `hybrid-asof-ministry-v2.1-gold34.json` (0.31, 0.47, 0.53 at K = 5, 10, 20).

## Cases

The 17 cases with an essential provision outside the baseline's top 20: A1, A2, A3, A4, A5, A6, A7, A9,
A10, A11, A14, A15, A16, A20, A22, R4, L4. They hold 30 such provisions ("missed provisions").

## Oracle queries

One query per missed governing issue, 1 to 4 per case, in `oracle-queries.json`. Drafted by Claude from
the gold answer and the missed provisions, then reviewed by Le Hung against these rules:

1. Vietnamese, as a practitioner would search, at most 20 words.
2. It may name the legal subject and the law by its common name ("Luật Quản lý thuế", "thuế suất thuế
   GTGT"), but never a document number, an article or clause number, or a date.
3. It must not copy 4 or more consecutive words from the provision's text. `measure_oracle.py` checks
   this and reports each query's longest copied run; a query that breaks it is rewritten, not dropped.
4. It names the issue, not the case's facts or answer (no amounts, rates, or outcomes).

## Measures

- **M1, recoverable:** for each missed provision, its best rank over the case's oracle queries, each
  searched alone with the case's filters. Reported as the share of the 30 found at K = 5, 10, 20.
- **M2, merged:** the question's ranking and its oracle rankings fused by reciprocal rank (equal weight),
  scored as essential recall over all essential provisions of all 30 scored cases (cases without oracle
  queries keep their baseline ranking), compared case by case with the baseline.

## Decision rule (fixed now)

- M1 at K = 10 of 50% or more: the bottleneck is naming the issue. Build item 16, with M2 as its ceiling.
- M1 at K = 10 of 25% or less: the bottleneck is retrieval. Study the unrecovered provisions' wording,
  OCR, and chunking before any issue step.
- In between: both; report the split by miss category (needs an unstated step, buried by facts, worded
  differently).

## Runs

Each run takes minutes on a laptop and makes no model calls. The draft queries are run once and
reported as **draft**. The result is the run after Le Hung's review; both are kept. The queries are not
changed after the reviewed run.

## Change after writing (24/11/2026)

Le Hung, short of time, asked for a first-pass review by a Claude agent, which he then checks
([review.md](review.md)). The agent did not see the draft runs. The reviewed run is still the one after
his check, and it is run once.
