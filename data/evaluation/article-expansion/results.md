# Item 20, article expansion: results

## Phase 1 (24/11/2026)

`phase1.py --window 2500`, run once, report `runs/article-expansion-2500.json`. The 30 scored cases,
evidence chosen as answers choose it (5 located passages), live filters, endings list after item 19.

| | Essential recall of the 5 passages |
| --- | --- |
| Without expansion | 0.35 |
| With expansion (2,500-character window) | **0.43** |

**+0.08: by the plan's rule (+0.06 or more), go to phase 2.** 3 cases up (A18, A19, A21), none down.
Expansion adds about 3,000 characters an answer to about 6,500 today, within the five windows' 12,500.
(The 0.35 without expansion is above the 0.31 of the plain top 5 because answers skip unlocated passages.)

The gain is narrower than the article ceiling (0.43 there too, but at K = 5 of the raw list): the
window holds the target clause when it is a short neighbour; long articles (VAT Law Art 5) do not fit.

## Phase 2 (24/11/2026)

Expansion built into answers (prompt and fact check read the filled window; a window holding other
clauses is cited at article level), the 15 graded questions answered and graded once:
`grade_answers.py --cases-from answers-gold-v1-2026-11-23c.json`, report
`runs/answers-gold-v1-2026-11-24-expansion.json`. About $0.03.

| | Correct | Partly | Wrong | Refused |
| --- | --- | --- | --- | --- |
| Without expansion (`-23c`) | 8 | 0 | 2 | 5 |
| With expansion | 6 | 2 | 3 | 4 |

**By the plan's rule (2 more correct, or 2 fewer wrong plus refused, with wrong at most 2), expansion
stays out of answers.** A3 and L3 fall from correct to partly: with more of the article in view the model
adds a wrong deadline (A3) or hedges between two documents (L3). A4 moves from refused to wrong: it now
answers, but without the repayment and interest the reference requires. A one-answer change is within
run-to-run variation; three, all in one direction, are not.

Answers also took 45 s on average against 7.5 s on 23/11, from the laptop. Not investigated, since the
change is not shipped: part is the extra article queries, part may be the provider that day.

The implementation is kept as [answers.patch](answers.patch) (`git apply` from the repository root).
Retrieval holds more of the right law with expansion; answers do not use it better. A later try would
need the model to read the added clauses as context, not as statements to report, and its own plan.
