# Oracle issue experiment: results (draft queries)

Run 24/11/2026 with `scripts/measure_oracle.py`, plan in [plan.md](plan.md). **Draft**: the queries in
`oracle-queries.json` still await Le Hung's review; the result counts only after it. Correction to the
plan: the 17 cases hold **32** provisions outside the top 20, not 30 (a miscount when writing it).

## Runs

| Run | Queries | M1 recovered at K = 5 / 10 / 20 | M2 merged recall at K = 5 / 10 / 20 |
| --- | --- | --- | --- |
| `oracle-draft-unchecked` | First drafts; 17 of 30 copied 4-5 words, mostly terms of art | 0.19 / 0.25 / 0.50 | 0.31 / 0.47 / 0.64 |
| **`oracle-draft`** | All 30 within the copy rule | **0.19 / 0.25 / 0.47** | **0.29 / 0.47 / 0.62** |

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
