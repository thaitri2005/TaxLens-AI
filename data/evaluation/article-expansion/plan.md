# Item 20, article expansion: plan

Written 24/11/2026, before any expansion figure was computed. Follows the
[study of the 10 misses](../misses/ten-misses.md): counting a provision as found when any passage of its
article is in the top K gives 0.43 against 0.31 at K = 5. That ceiling assumes whole articles; this plan
measures a capped design that costs no more prompt than today.

## The design

Answers send 5 located passages, each cut at 2,500 characters (`qa.py`, prompt and fact check). Most
clause passages are 100-1,500 characters. Expansion fills each evidence passage's window with its own
article: the passage, then the other passages of the same document version and article, nearest clause
first (next, previous, then outward), each whole or not at all, until 2,500 characters. The passage stays
the one cited, at article level when text from a sibling is used; the fact check reads the same filled
window. Search and ranking are unchanged.

Variant, tried only if the decision rule below asks for it: a 5,000-character window (about twice the
prompt, about $0.001 more per answer).

## Phase 1: retrieval ceiling of the capped design (laptop, about 4 minutes, no model calls)

The 30 scored cases, live filters, endings list after item 19. Evidence chosen as answers choose it
(hybrid top 20, located passages, `prefer_not_ended`, first 5). A provision counts as found when a
passage holding it is in the 5 or in the text expansion adds to them.

- **Measure:** essential recall of the 5, without and with expansion; case by case up, down, same; the
  added characters per answer.
- No ranking changes, so nothing can go down; a case going down means a bug.

## Phase 2: answers (only if phase 1 says so)

The 15 graded questions, answered once with expansion, graded once by the same judge
(`grade_answers.py`), against `answers-gold-v1-2026-11-23c` (8 correct, 2 wrong, 5 refused). About 6
minutes and $0.03. Judge and model vary from run to run by about one answer, so a one-answer change is
noise.

## Decision rules (fixed now)

- **Phase 1, window 2,500:** +0.06 or more over the 5 without expansion: go to phase 2. Less than +0.03:
  try the 5,000 window once by the same rule; if it also stays under +0.03, drop item 20. In between: go
  to phase 2 with 2,500.
- **Phase 2:** ship if correct goes up by 2 or more, or wrong plus refused goes down by 2 or more, with
  wrong not higher than 2. Otherwise keep it out of answers and record why.

Each phase is run once and recorded in [retrieval-experiments.md](../../../docs/retrieval-experiments.md).
