# Evaluation status

Where retrieval evaluation stands as of 05/11/2026. This page is rewritten as things change;
the dated record behind each figure is in
[retrieval-experiments.md](retrieval-experiments.md).

## Summary

- Gold set: `gold-v1.0 --verified-only`, 12 scored cases. That is too few to show most
  differences, so wins and losses are given with every comparison.
- The keyword term limit was the largest problem found. Removing it nearly tripled hybrid recall
  at K = 10, from 0.15 to 0.41. The change is in the code, with a faster query that returns the
  same results. It went live on 05/11/2026 (`158c4c2`).
- Hybrid and keyword search are now close, and these cases cannot separate them. Issue-guided
  retrieval has fallen behind both.
- Of hybrid's 20 misses at K = 10, 14 are nowhere near the top, and 7 of those need a legal step
  the question does not state. Better word matching cannot reach them.
- More documents alone do not fix retrieval: adding the two missing circulars made only one of
  three affected cases findable until the limit was removed.

## What the limit changed

From 17/10/2026, when the search overhaul added `MAX_KEYWORD_TERMS = 12`, until 05/11/2026, keyword
search saw only the first 12 terms of a question. Before the overhaul it required every word of a
question to appear in one passage, and returned nothing for most natural questions. So long
questions had not had working keyword search at any point before this fix. This affected the live
site's search and answers, and every gold-set experiment.

It went unnoticed because the older regression set has short questions (at most 15 terms), while
the gold questions have up to 40, and all 12 scored ones were cut. Keyword search scoring exactly 0
on the gold set was the visible sign.

| Earlier conclusion | Under the limit | Without it |
| --- | --- | --- |
| Baseline hybrid recall at K = 10 | 0.15 | 0.41 |
| Keyword search alone | 0 at every K | 0.42 at K = 10, close to hybrid |
| Issue-guided against hybrid at K = 10 | Ahead, 0.21 against 0.15 | Behind, 0.17 against 0.41 |
| Filter for ended documents, hybrid at K = 10 | 0.15 to 0.26 | 0.41 to 0.45 |
| L2 | Not found, though its circular was loaded | Found at rank 5 |

**What this does not show.** The gain rests on 12 cases and repeats a result already seen. It
measures retrieval, not answers, and more than half of the essential provisions are still missed at
K = 10. The article-level regression scores do not change.

## Corpora

The database holds `corpus-v1.2`. Manifests are in `data/evaluation/corpus/`.

| Corpus | What it is | Documents | Passages | Fingerprint |
| --- | --- | --- | --- | --- |
| `corpus-v1` | Original frozen corpus | 2,026 | 61,208 | `317f5a0d` |
| `corpus-v1.1` | With 8 PDFs reprocessed to repair split syllables | 2,026 | 61,204 | `cd396fa3` |
| `corpus-v1.2` | With Circulars 80/2021 and 25/2018 added | 2,028 | 62,182 | `7df84879` |
| `corpus-v2` | Selected, not collected: 975 more documents, about 20 hours ([rules](corpus-inclusion.md)) | | | |

A run against `corpus-v1` now stops at its corpus check. The 8 PDFs' earlier passages and
embeddings are saved in `data/local/backups/corpus-v1-8pdfs.json`, which is not committed.

## Results

Essential recall over provisions held in the corpus, on `corpus-v1.2` with `--as-of case` and no
term limit. Full coverage is in brackets where it is not 0.

| Method | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| Keyword | 0.22 (0.08) | 0.42 (0.25) | 0.42 (0.25) |
| Semantic (no terms, so unaffected) | 0.11 | 0.13 | 0.30 (0.08) |
| **Hybrid** | **0.30 (0.08)** | **0.41 (0.17)** | **0.45 (0.25)** |
| Hybrid, filter | 0.41 (0.17) | 0.45 (0.25) | 0.45 (0.25) |
| Hybrid, ministry dates only | 0.34 (0.08) | 0.45 (0.25) | 0.45 (0.25) |
| Issue-guided | 0.10 | 0.17 | 0.28 |
| Issue-guided, filter | 0.22 | 0.28 | 0.45 (0.17) |
| Issue-guided, ministry dates only | 0.17 | 0.24 | 0.41 (0.08) |

"Filter" leaves out documents that had ended by the case date, including two inferred rules that no
legal expert has validated. "Ministry dates only" leaves out that inference. Figures under the limit
of 12 are in [the results](retrieval-experiments.md#removing-the-keyword-term-limit-results-05112026).

## What each experiment found

| Experiment | Finding | Standing |
| --- | --- | --- |
| Keyword term limit | Hybrid at K = 10 rises from 0.15 to 0.41: 6 wins, 0 losses, p = 0.03. Keyword rises from 0 to 0.42: 8 wins, 0 losses, p = 0.008 | Live. Repeats a result already seen, so new cases are needed as independent evidence |
| Query time | Keyword search takes 1.7 s a question, against 17 s with the old query and 7 s under the limit. Results are identical | Live, with migration `20261105_0006` recorded. Timed from a laptop, not yet on the site |
| Issue-guided against hybrid | Hybrid is ahead without the limit: at K = 10 issue-guided wins 1, loses 5, p = 0.22. Taking turns between rankings pushes the question's own results down | Not worth using as it is; a different merge would need its own plan |
| Filter for ended documents | Hybrid wins 3, loses 0 at K = 5, p = 0.25, and changes one case at K = 10. Removes no gold document | Smaller effect than before; the gain depends on unvalidated rules |
| The ministry's expiry dates | Hybrid gets the same recall as the full filter at K = 10 and 20, and part of it at K = 5, without inference | The conservative version of the filter |
| Two missing circulars | A7 and L2 found; A4 not, since Art 40(3) is worded differently from the question | Loaded |
| Why 14 provisions are not retrieved | 7 need an unstated legal step, 6 share words but the facts bury them, 1 is worded differently. Term weighting and expanding abbreviations reach none of them | Grouping not reviewed by an expert. Points to working out the legal issues first |
| Leaving forms out of search | No recall gain, and 1 rank moved by one. Forms leave the top 50 entirely (22 before) | In the code, not yet released. Kept for what readers and the model see |
| Keeping vector search exact | Same results; rules out silently returning at most 40 candidates | In the code, not yet released |
| Making search faster | A hybrid search takes 1.5 s, against 2.8 s, with identical results. Drops an unused 121 MB index | In the code, not yet released |
| Split-syllable repair | Almost no rank changed | Kept for correct text, not a retrieval gain |
| Following one legal reference | Reaches 1 of 20 missed provisions at K = 10, at document level only | Not worth building now |

## Open work

In suggested order:

1. Add more gold cases, since 12 cannot separate most methods and the limit result needs independent
   evidence.
2. Plan a step that works out which legal issues a question depends on, since 7 of the 14
   unretrieved provisions need one ([diagnosis](retrieval-experiments.md#why-14-provisions-are-not-retrieved-05112026)).
3. Have a tax expert review the inferred rules, the 178 documents the ministry lists as in force
   but our list ends, the alternative valid evidence sets, and whether Circular 80/2021 Art 40(3)
   still applied on A4's date.
4. Fix the article labels of forms, so that a form in Circular 80/2021 no longer reads as Art 89.
   This needs reprocessing and a new corpus version. Search already leaves forms out unless asked.
5. Decide on `corpus-v2`, because more passages add competition for the top ranks. It needs a
   database backup, Airflow, and a go-ahead.
