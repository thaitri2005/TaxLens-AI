# Already tried

**Read this before starting any run.** It lists what has been tried, so nothing is paid for twice.
Reports are in `data/evaluation/runs/`. Fuller write-ups of everything before 06/11/2026 are in git
(`git show 3384ffc:docs/retrieval-experiments.md`). Current results are in
[evaluation-status.md](evaluation-status.md).

Before running anything: read this page, state the size and expected time, prefer analysing saved
reports, and run paid or slow tests once.

## How to read the figures

- Figures are essential recall at K = 5, 10 and 20 on the same 12 scored gold cases
  (`gold-v1.0 --verified-only`, `--as-of case`). Differences of a case or two prove little.
- Everything dated before 05/11/2026 ran with keyword search cut to 12 terms, and everything before
  06/11/2026 with unconverted TCVN3 text. Old comparisons between methods do not stand; the verdicts
  below take this into account.
- `compare_retrieval_runs.py` refuses reports from different corpora, so comparisons across corpora
  have no p-value.

## Retrieval

| Tried | Result | Verdict | Reports |
| --- | --- | --- | --- |
| Removing the 12-term keyword limit (now 64) | Hybrid 0.11, 0.15, 0.22 → 0.30, 0.41, 0.45 (K = 10: 6-0, p = 0.03). Keyword 0 → 0.42 (8-0, p = 0.008). Saw the result before the plan, so not independent | **Live** | `*-nolimit` |
| Issue-guided retrieval: a search per legal issue, interleaved with the question's | Behind hybrid: K = 10 1-5, p = 0.22. On `corpus-v2` 0.04, 0.10, 0.15. Taking turns pushes the question's own rank 5 down to about 16-21 | **Do not rerun.** Only a different merge, with its own plan and new cases, is worth trying | `issue-guided-*` |
| Filter for ended documents, all rules, `corpus-v1.2` | Hybrid 0.38, 0.45, 0.45. Removes no gold document | Works, not on the site | `hybrid-asof-repeals-noforms` |
| The same, list built from `corpus-v1`, on `corpus-v2` | Hybrid 0.23, 0.35, 0.45. Issue-guided 0.06, 0.10, 0.26. The list misses the new documents | Superseded | `*-asof-repeals-v2` |
| **The same, list rebuilt for `corpus-v2`** (825 ended documents) | **Hybrid 0.35, 0.45, 0.45.** 9 provisions up, none down. The list was built after seeing the problem, and includes unvalidated rules | Best result. Not on the site | `hybrid-asof-repeals-v2list` |
| Filter, explicit statements only (`corpus-v1`, under the limit) | No provision gained | Stale. Not worth repeating alone | `*-repeals-explicit` |
| Filter, explicit + ministry dates (`corpus-v1.2`) | Hybrid 0.34, 0.45, 0.45, needs no inference | The conservative option. **Untested on `corpus-v2`** (one run, about 6 minutes) | `*-ministry-nolimit` |
| Following one legal reference from top passages | Reaches 1 of 20 missed provisions, at document level | Not worth building | `reachability-*` |
| Rare terms weigh more (IDF), and expanding abbreviations (`GTGT`) | Hybrid K = 5 falls to 0.10 with IDF; K = 10 gains one provision outside the hard 14. Neither reaches any of the 14 | Do not adopt | Exploratory, not kept |
| Taking more candidates | The 14 hardest provisions rank 127 or worse in the vector list, 315 or worse by keyword | Would not help | Diagnosis below |
| Leaving forms out | No recall change, 1 rank moved. Forms leave the top 50 (22 before) | **Live**, for what readers see | `*-noforms` |
| Repairing split syllables in 8 PDFs | 10 of 11 provisions keep their rank | Kept for correct text, no retrieval gain | `corpus-v1.1` runs |
| Adding Circulars 80/2021 and 25/2018 | A7 and L2 found; A4 not | Loaded | `*-asof-v1.2` |
| More documents (`corpus-v2`) without a filter | Hybrid 0.10, 0.30, 0.41, because ended documents crowd the top | See the filter above | `*-asof-v2` |

**Why 14 provisions are never retrieved** (hybrid, `corpus-v1.2`, our reading, not an expert's). 7 need
a legal step the question has no words for (A1 VAT Law 9(3), Decree 174/2025 1(1); A4 Tax
Administration Law 47, 59, Circular 80/2021 21; A7 Law 64/2025 58(1), Decree 181/2025 38(1)). 6 share
legal words but the facts bury them (A2, A6, A9). 1 is worded differently (A3). Stored issue queries
reach only the 2 from A2. So better word matching cannot fix half of them; it needs a step that works
out the law a question depends on.

## Speed

| Tried | Result | Verdict |
| --- | --- | --- |
| Counting terms from indexes, ranking only passages that can reach the top | Keyword 17 s → 1.7 s, identical results | **Live** |
| Vector search choosing from ids first; dropping the HNSW index | Hybrid 2.8 s → 1.5 s on `corpus-v1.2`, 121 MB saved | **Live** |
| Exact vector search (`distance + 0`) | HNSW could silently return at most 40 candidates | **Live** |
| Raising `work_mem` | No real gain | Do not repeat |
| Scanning only rare terms; running both searches at once | First changes results; second saves at most 0.2 s | Not done |
| Shorter answers, to cut the model's 46-91 s | Would be about 25-30 s | **Declined by the owner, 06/11/2026** |
| Faster cheap models | One call each: gemma-3-27b 16 tokens/s, gemma-3-12b 21, Llama 3.1-8B 22. About 25% at best | Not worth switching |

## Answer models

| Model | Result |
| --- | --- |
| `Qwen/Qwen3-4B-Instruct-2507` | Gone from the router by 06/11/2026: status 400 |
| `Qwen/Qwen3.5-9B` | Failed all 5 questions. It reasons at length first, likely using up the tokens (not confirmed). Avoid reasoning models |
| **`google/gemma-3-27b-it`** | **Current.** 5 of 5 answered, chosen as cheap and suitable, not by comparison. About $0.01 for 5 questions |

Answer run on `corpus-v2`: faithfulness and citation completeness 1.0, relevancy 0.75-0.93, context
precision 1.0 on 4 of 5. These checks are lexical and cannot see if an answer is right. Read by hand,
answers can rest on ended law (Decree 123/2008, Law 13/2008, Circular 32/2011).

## Text and corpus

| Tried | Result | Verdict |
| --- | --- | --- |
| OCR `vie` against `vie+eng`, fast against best models | `vie` fast: word match 0.975, 2.7 s a page. Best model is twice as slow for nothing | **`vie` fast is live** |
| OCR DPI and page modes | 300 DPI, mode 6 is best (word error 25.6%, against 31.7% at 144 DPI) | **Live** |
| Re-OCR of 576 older scans | About 1.5 points of word match for 24,000 pages | Not done, on purpose |
| Mass correction of OCR typos | No dependable corrector; a model could change a statute's meaning | Rejected |
| Smaller passage size | Few articles exceed the embedding limit once TCVN3 is converted; needs a full re-embed | Rejected, no evidence |
| Excel parser for the 7 workbooks filed as `.rtf` | Old tariff tables | Not worth it |
| TCVN3: gating conversion on a share of the document | Blocks mixed-font RTFs, leaving 392 passages | Replaced with per-file rules |
| TCVN3: treating `µ` as a symbol | Turned `hành` into `hµnh` | Replaced with position rules |
| TCVN3: converting OCR text | `Ghi chú: ¬¬` became `Ghi chỳ: ơơ` | OCR text is never converted; a PDF layer only if mostly TCVN3 |
| Word-count check for over-long passages | Reported 16 when tokens gave 9,964 | Count tokens |
| Accent share as a check for good text | TCVN3 characters count as accents, which hid the bug | Do not rely on it |
| Trusting a test's failure count | The 20-document trial passed with 16 holding TCVN3 | Read sample output |
| Listing the ministry database across all fields | Stopped after 39 minutes, no number filter | Page by document type instead, about 45 minutes |
| vbpl.vn, commercial legal databases | Unresponsive; terms forbid collection | Not used |

## What runs cost

From a laptop against Azure, on `corpus-v2`. The database is 965 MB on 2 GB of memory.

| Run | Time | Credits |
| --- | --- | --- |
| Keyword baseline | About 100 s | None |
| Hybrid baseline | 6-9 minutes | None |
| Issue-guided baseline | 8-23 minutes | None |
| `freeze_corpus.py` | 30 s | None |
| `extract_repeals.py` | 100 s | None |
| 5 answer questions | About 6 minutes | About $0.01 |
| Full collection build, 10 rounds of 100 | 13.7 hours | None |
| OCR, embedding | About 2.5 s a page, 0.3 s a passage | None |

Hybrid baselines take 29-47 s a question although retrieval inside an answer takes 3-6 s. This is
unexplained.

**Things that wasted runs:** a laptop IP change (check `curl https://api.ipify.org` against the
firewall first), internet drops (runs start over, so use a steady connection), and short `timeout`
values that killed a run and lost its output.
