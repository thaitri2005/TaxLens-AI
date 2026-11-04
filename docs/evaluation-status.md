# Evaluation status

Where retrieval evaluation stands as of 05/11/2026. This page is rewritten as things change;
the dated record behind each figure is in
[retrieval-experiments.md](retrieval-experiments.md).

## Summary

- Gold set: `gold-v1.0 --verified-only`, 12 scored cases. That is too few to show most
  differences, so wins and losses are given with every comparison.
- The keyword term limit is the largest problem found. Removing it nearly tripled hybrid recall
  at K = 10 in an exploratory run. **The fix is not in the code yet**, and the run needs
  repeating under a written plan.
- More documents alone do not fix retrieval: adding the two missing circulars made only one of
  three affected cases findable.

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

Essential recall over provisions held in the corpus, on `corpus-v1.2` with `--as-of case`. Full
coverage is in brackets where it is not 0.

| Method | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| Keyword, limit of 12 terms | 0 | 0 | 0 |
| Semantic | 0.11 | 0.13 | 0.30 (0.08) |
| Hybrid, limit of 12 | 0.11 | 0.15 | 0.22 |
| Hybrid, limit of 12, with filter | 0.13 | 0.26 (0.08) | 0.34 (0.17) |
| Issue-guided, limit of 12 | 0.15 | 0.21 | 0.26 |
| Issue-guided, limit of 12, with filter | 0.26 | 0.28 | 0.30 |
| **Hybrid, limit of 40 (exploratory)** | **0.30 (0.08)** | **0.41 (0.17)** | **0.45 (0.25)** |

"With filter" leaves out documents that had ended by the case date, including two inferred rules
that no legal expert has validated. Issue-guided search and the filters have not been run without
the limit.

## What each experiment found

| Experiment | Finding | Standing |
| --- | --- | --- |
| Keyword term limit | Hybrid at K = 10 rises from 0.15 to 0.41: 6 wins, 0 losses, p = 0.03 | Strong lead, exploratory, not yet in the code |
| Filter for ended documents | Hybrid at K = 10 wins 3, loses 0, p = 0.25, and removes no gold document | Promising; the gain depends on unvalidated rules |
| The ministry's expiry dates | Without inference, about half of hybrid's filter gain and all of issue-guided's at K = 10 and 20 | The conservative version of the filter |
| Issue-guided against hybrid | Wins 2, loses 0 at K = 10, p = 0.5, measured on `corpus-v1` | Unresolved; repeat without the limit |
| Two missing circulars | A7 found, L2 and A4 not (L2 is found once the limit is removed) | Loaded |
| Split-syllable repair | Almost no rank changed | Kept for correct text, not a retrieval gain |
| Following one legal reference | Reaches at most 1 of 20 missed provisions at K = 10 | A small supplement; repeat without the limit |

## Open work

In suggested order:

1. Write a plan, remove the term limit in `retrieval/search.py`, check query time and the older
   regression datasets, and rerun every method and filter. This also changes search on the site.
2. Add more gold cases, since 12 cannot separate most methods.
3. Have a tax expert review the inferred rules, the 178 documents the ministry lists as in force
   but our list ends, the alternative valid evidence sets, and whether Circular 80/2021 Art 40(3)
   still applied on A4's date.
4. Handle forms and appendices such as `80/2021` Art 89's 592 passages, and multi-step cases such
   as A4's interest provision.
5. Decide on `corpus-v2` after step 1, because more passages add competition for the top ranks.
   It needs a database backup, Airflow, and a go-ahead.
