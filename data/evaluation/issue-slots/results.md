# Item 16, issue slots: results

24/11/2026, phase 1 of the [plan](plan.md), from the saved counted oracle run (`oracle-reviewed.json`);
`slot_ceiling.py`, output in `ceiling.json`. No search, no model calls.

| Evidence budget | Question only | Slots: question top `q` + each issue's top `s` | Best gain |
| --- | --- | --- | --- |
| **5** (answers today) | 0.31 | `q = 2, s = 1`: 0.33 (2 up, 0 down); `q = 3, s = 1`: 0.33 (1 up) | **+0.025** |
| 8 | 0.41 | `q = 4, s = 1`: 0.43 (2 up); `q = 3, s = 2`: 0.46 (4 up, 0 down) | +0.05 |

**By the plan's rule (less than +0.05 at a budget of 5), item 16 is dropped.** Even with hand-named
issues, a slot rarely holds the missing provision: the named issue's search puts it in its top 5 for 28%
of the missed provisions, but first for few. Phase 2 (a model naming the issues) is not run.

Approximation as planned: ranks count unlocated passages and duplicates between lists are not skipped.
Neither changes the verdict at this margin.

What this leaves: the misses are about ranking within a search, not about which searches are made. The
10 provisions not found even when named, and the documents with no ending stated (166/2013, 194/2010),
are where retrieval can still gain.
