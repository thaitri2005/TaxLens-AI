# Oracle issue experiment: results (draft queries)

Run 24/11/2026 with `scripts/measure_oracle.py`, plan in [plan.md](plan.md). **Draft**: the queries in
`oracle-queries.json` still await Le Hung's review; the result counts only after it. Correction to the
plan: the 17 cases hold **32** provisions outside the top 20, not 30 (a miscount when writing it).

## Runs

| Run | Queries | M1 recovered at K = 5 / 10 / 20 | M2 merged recall at K = 5 / 10 / 20 |
| --- | --- | --- | --- |
| `oracle-draft-unchecked` | First drafts; 17 of 30 copied 4-5 words, mostly terms of art | 0.19 / 0.25 / 0.50 | 0.31 / 0.47 / 0.64 |
| **`oracle-draft`** | All 30 within the copy rule | **0.19 / 0.25 / 0.47** | **0.29 / 0.47 / 0.62** |
| `oracle-draft-item19` | The same, endings list after item 19 (24/11/2026) | 0.25 / 0.28 / 0.53 | 0.31 / 0.47 / 0.64 |

Baseline (the question alone): 0.31 / 0.47 / 0.53. M2 against it, case by case: K = 5 none up, one down;
K = 10 two up, two down; K = 20 four up, one down.

## Reading

**By the plan's rule (M1 at K = 10 of 25% or less) the bottleneck is retrieval, not naming the issue.**
Told the right issue, search still leaves 75% of the missed provisions out of the top 10 and 17 of 32 out
of the top 20. Merging the issue searches with the question only helps deep in the list (K = 20).

Why named issues still fail, from the top results of the unrecovered queries:

1. **Old law the endings list does not know** outranks current law: Decree 158/2003 and Law 07/2003 on
   VAT, Decree 129/2013 and Circular 166/2013 on penalties, Circular 41/2006, Decree 18/2009. All were
   replaced long ago, but nothing in the corpus says so in a form the rules read.
2. **Untitled old texts** without articles (`89/98/TT/BTC`, `833/TC/TCT`, `27/TCT`) match almost any
   wording.
3. **Wording** matters little: the first drafts used the terms of art and recovered about as much
   (0.50 against 0.47 at K = 20).

So item 16 (naming the governing law) would not pay before retrieval keeps superseded law out of the
way. The next step is the endings list's reach to old documents (for example, a document replaced by a
later one on the same subject from the same issuer), then this oracle again.

## After item 19 (24/11/2026)

Most of that superseded law had an explicit ending the rules could not read (158/2003, 07/2003, 18/2009,
21/2012; 129/2013 is ended only in part, rightly kept). With 30 more endings, the baseline is identical
case by case, and M1 at K = 10 is 28%: now just inside the plan's middle band (25-50%), so both causes
count. L4 and A7 recover provisions; 15 of 32 stay outside the top 20. Their top 10 is now held by
documents with no ending stated anywhere in the corpus: the 2013 penalties circular 166/2013, the 2010
customs circular 194/2010, 123/2004, 176/2010, and 1990s ministry texts (`27/TCT`, `101 TC/TCT`), plus
current law on neighbouring subjects. Only an outside status source, or the inferred rules once a tax
expert validates them, can end these.

## Review (24/11/2026)

A first-pass review by a Claude agent, blind to the runs above, is in [review.md](review.md): 7 drafts
broke the 20-word rule, 9 more mis-stated the issue or its term, and one provision had no query. The
proposed queries (`oracle-queries-reviewed.json`) have not been run. Le Hung checks them first, then one
run gives the result.
