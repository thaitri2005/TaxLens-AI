# Item 16, issue slots: plan

Written 24/11/2026, before any slot figure was computed. Follows the counted oracle run
([results](../oracle/results.md)): named well, an issue finds 28% of the missed provisions in its own top
5, but fusing the issue searches into the question's list leaves recall at K = 5 unchanged (0.31). So
item 16 is redesigned: each named issue gets its own places in the evidence, instead of one fused list.

## The design

Answers use 5 evidence passages, the first located ones among 20 candidates (`qa.py`). With slots, the
evidence is the question's top `q` passages plus the top `s` of each issue's search, in issue order, up to
a total budget `B`; a passage already taken is skipped. A case with no issues keeps the question's top
`B`.

## Phase 1: ceiling with the oracle issues (free, from saved runs)

Inputs fixed: `data/evaluation/runs/oracle-reviewed.json` (reviewed queries, endings list after item 19)
and its baseline `hybrid-asof-ministry-v2.1-gold34-item19.json`; no new search.

- **Measure:** essential recall over the 30 scored cases when the evidence is chosen as above, for
  `B = 5` (`q = 2, s = 1`; `q = 3, s = 1`) and `B = 8` (`q = 4, s = 1`; `q = 3, s = 2`), against the
  question's top `B` alone. Case by case: up, down, same.
- **Approximation:** saved runs hold each provision's rank, not passage ids, so duplicates between lists
  are not skipped (slightly pessimistic), and ranks count unlocated passages (answers skip those, slightly
  optimistic). Stated with the result.

## Decision rule (fixed now)

Judged on `B = 5`, the answers' budget, best of its two splits:

- **+0.10 or more** over the question's top 5 (0.31): worth building. Go to phase 2.
- **Less than +0.05:** drop item 16; the issue step cannot pay even with perfect issues.
- **In between:** report, and look at `B = 8` before deciding (a larger evidence budget costs model
  tokens, about $0.001 an answer).

## Phase 2, only if phase 1 says so

A model names the issues (the same rules as the oracle queries, generated, not hand-written) for the 30
scored cases: one call each, about $0.01 in all. The same slot measure, against the oracle ceiling. Then
answers on the 15 graded questions, once, against `answers-gold-v1-2026-11-23c` (8 correct, 2 wrong, 5
refused). Each phase is run once and recorded in [retrieval-experiments.md](../../../docs/retrieval-experiments.md).
