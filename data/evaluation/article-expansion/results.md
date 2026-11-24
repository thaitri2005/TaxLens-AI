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
