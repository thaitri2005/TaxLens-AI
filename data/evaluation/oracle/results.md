# Oracle issue experiment: results

Run 24/11/2026 with `scripts/measure_oracle.py`, plan in [plan.md](plan.md). **The result is the counted run
with reviewed queries, at the end of this page**; the sections before it are the draft runs. Correction to the
plan: the 17 cases hold **32** provisions outside the top 20, not 30 (a miscount when writing it).

## Runs

| Run | Queries | M1 recovered at K = 5 / 10 / 20 | M2 merged recall at K = 5 / 10 / 20 |
| --- | --- | --- | --- |
| `oracle-draft-unchecked` | First drafts; 17 of 30 copied 4-5 words, mostly terms of art | 0.19 / 0.25 / 0.50 | 0.31 / 0.47 / 0.64 |
| **`oracle-draft`** | All 30 within the copy rule | **0.19 / 0.25 / 0.47** | **0.29 / 0.47 / 0.62** |
| `oracle-draft-item19` | The same, endings list after item 19 (24/11/2026) | 0.25 / 0.28 / 0.53 | 0.31 / 0.47 / 0.64 |

Baseline (the question alone): 0.31 / 0.47 / 0.53. M2 against it, case by case: K = 5 none up, one down;
K = 10 two up, two down; K = 20 four up, one down.

## Reading of the draft run (superseded by the counted run)

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
way. The next step was the endings list's reach to old documents, then this oracle again: both done
below (item 19, then the counted run).

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
proposed queries (`oracle-queries-reviewed.json`) were accepted by Le Hung and run once, below. The draft
readings above are superseded by it.

## Counted run: reviewed queries (24/11/2026)

**This is the experiment's result.** Le Hung accepted the first-pass review as proposed, open points
left as written. Before the run the copy check found one 4-word run (A2.2), reworded; the queries were
then frozen (`9d9fc97`) and run once: `oracle-reviewed.json`, endings list after item 19.

| | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| M1: the 32 missed provisions found by the named issue alone | 28% | **38%** | 69% |
| M2: question and issues fused, recall over 30 cases | 0.31 | 0.49 | 0.60 |
| Baseline, the question alone | 0.31 | 0.47 | 0.53 |

M2 against the baseline, case by case: K = 5 none up or down; K = 10 three up, two down; K = 20 four up,
one down.

**Reading.**

1. **M1 at K = 10 is 38%, in the plan's middle band (25-50%): both causes count.** Named correctly, an
   issue finds 12 of the 32 in the top 10 and 22 in the top 20. 10 are not found even then: VAT Law 9(3)
   and 5(1), Decree 181/2025 4(1) and 38(1), Tax Administration Law 44(1) and 59, Law 64/2025 58(1), PIT
   Law 7(4), and Law 108/2025 16(1) (twice). Those are retrieval failures.
2. **The legal term matters more than the draft suggested.** Against the same queries in their draft
   wording (`oracle-draft-item19`), M1 rises from 25%, 28%, 53%. Most of the gain is the term of art:
   "tiền chậm nộp" instead of "lãi phạt nộp thuế muộn" (A15, A16), "hàng xuất khẩu" (A20), "khai bổ
   sung" (A4), "không bị phạt" instead of "miễn xử phạt" (A9).
3. **Fusing issue searches into one list barely moves what answers use.** M2, the ceiling of item 16 as
   planned, leaves K = 5 at 0.31 and adds 0.02 at K = 10; the gain is at K = 20. Answers take their
   evidence from the first located passages of 20, so item 16 as an equal-weight fused list would not
   pay. The issue searches themselves put 28% of the missed provisions in their own top 5: what fusion
   loses is their top few. A design that gives each named issue its own evidence slots would use that,
   and needs its own plan and ceiling.

The split by miss category the plan asks for in the middle band: of the 7 provisions the earlier
diagnosis said need an unstated legal step, 2 are found in the top 10 when named (Decree 174/2025 1(1),
Circular 80/2021 21); of the 8 buried by the case's facts (A2, A6, A9), 4; the 1 worded differently (A3)
is not found. The 16 provisions of the newer cases were not categorised.
