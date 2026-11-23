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
| Filter, explicit + ministry dates (`corpus-v1.2`) | Hybrid 0.34, 0.45, 0.45, needs no inference | Superseded by the `corpus-v2` run below | `*-ministry-nolimit` |
| **Filter, explicit + ministry dates, `corpus-v2`** (697 ended documents, `--repeal-rules explicit ministry`) | Hybrid 0.31, 0.42, 0.45. Against no filter, K = 10: 4 up, 1 down, p = 0.38. Against all rules: one provision behind at K = 5 and at K = 10. Removes no gold document. Misses Decree 123/2008, which only the guidance rule ends | **Live on the site** since 23/11/2026. Do not rerun | `hybrid-asof-ministry-v2` |
| Explicit rule reading lists split across passages, items after an OCR page number (`16 ¡) Thông tư ...`), and "tiếp tục có hiệu lực đến ngày" (ends the next day) | 29 more documents end (68/2019, 119/2018, 51/2010, tariff circulars ended by 182/2015 and 193/2012, 80/2021 from 01/07/2026); 714 confirmed. Each new entry read against its source list. Recall identical, case by case | **Live.** The list is `corpus-v2-ministry.json` as of `3f38db7` | `hybrid-asof-ministry-v2b` |
| Runs of replaced documents (`thay thế các Thông tư số X …, Y … và Z`; before, `các` broke the match and only the first number of a run or list item ended) | 33 more documents end, 14 guesses confirmed; the 30 new explicit entries each read against their sentence. Confirmed rules: 0.31, 0.42, 0.45, identical case by case. All rules: 0.38, 0.45, 0.45 (K = 5: A7, A8 up; K = 10: A1 up; none down) | **Live** (`8829e78`), list loaded on Azure | `hybrid-asof-ministry-v2.1-runs`, `hybrid-asof-allrules-v2.1-runs` |
| Newest-first list as a third fused list (weights 0.5, 1.0; documents ended by the question's date get nothing) | On the live refund question it lifted 59/2007, 194/2010, and 90/2002 (no recorded ending) to the top; VAT Law 48/2024 stayed out of the top 5. On a 2017 question it did drop 4/2009 | **Rejected** before a gold run: age cannot tell a replaced circular from one still in force | Not kept |
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
| Shorter answers, to cut the model's 46-91 s | Would be about 25-30 s | Not needed after the model change |
| Faster cheap models on ordinary providers | One call each: gemma-3-27b 16 tokens/s, gemma-3-12b 21-28, Llama 3.1-8B 22. About 25-70% at best | Not worth switching |
| **Hardware providers (Groq, Cerebras)** | gpt-oss-120b: 300-790 tokens/s. A whole answer takes 4-9 s, against 49-97 s | **Current** |
| Loading the embedding model at startup | Moves its load away from the first question. Not measured separately | **Current** |
| Loading the model without TensorFlow (`USE_TF=0`, set in `embeddings.py`), and counting article parts in one query per case | Model load 42 s → 21 s where TensorFlow is installed; a cached hybrid run 273 s → 193 s, results identical case by case | **Current** |
| Keyword query with no parallel worker (`SET LOCAL max_parallel_workers_per_gather = 0`); the database has one vCore | 29-term question 3.4 s → 2.4 s, identical results; evaluation identical case by case | **Current** |
| Keyword query: filtering versions once after grouping (materialized) instead of in every term scan | 3.6 s → 3.9 s: grouping all passages costs more than the repeated version scans | Rejected |
| **Smaller API image** (only `model.safetensors` of the 4 copies of the weights) | 1.92 → 0.77 GB compressed; image pull at cold start 35.1 s → 13.4 s. Embeddings identical | **Current** |
| **Resolving filtered versions first** (`_eligible_version_ids`), instead of joining documents into the passage scans | With a question's period: vector 10.0 s → 1.3 s, keyword with `current_on` 11.1 s → 3.6 s (laptop, warm). Retrieval evaluation identical case by case | **Current** |
| Filtering vector search (`current_on`, `as_of`) | Inside the database 3.0 s and 3.2 s, the exact scan of 144,600 embeddings either way; no filter 2.3 s from a laptop. The site's answers are not slowed by the ended-document filter | Nothing to fix |

## Answer models

| Model | Result |
| --- | --- |
| `Qwen/Qwen3-4B-Instruct-2507` | Gone from the router by 06/11/2026: status 400 |
| `Qwen/Qwen3.5-9B` | Failed all 5 questions. It reasons at length first, likely using up the tokens (not confirmed). Avoid reasoning models |
| `google/gemma-3-27b-it` | 5 of 5 answered, but 46-91 s in the model. About $0.0003 an answer |
| `google/gemma-3-12b-it` | 46 s on one question at 28 tokens/s |
| `openai/gpt-oss-20b` on Groq | 3-4 s, but one of 2 ran out of 2,000 tokens while reasoning. Cheaper than 120b; not chosen |
| **`openai/gpt-oss-120b`, `fastest` routing, 3,000 tokens** | **Current.** 5 of 5 answered through the app in 3.8-8.6 s, with 1.4-1.9 s in the model. About $0.002 an answer, by list price. It reasons first, and output reached 2,069 tokens, so 2,000 is too low |

**Graded against gold answers (23/11/2026):** 9 of 15 correct by a Qwen3-235B judge, 8 when read by
hand; `grade_answers.py`, report `answers-gold-v1-2026-11-23.json`. With documents that may have ended
used last in the evidence (`-23c`): 8 correct, 2 wrong, 5 refused, against 9, 4, 2. Do not rerun without
a change to answers or retrieval. The judge's provider allows 18 calls a minute; `--regrade` fills failed grades.

Answer run on `corpus-v2` with gpt-oss-120b: faithfulness and citation completeness 1.0, relevancy
0.67-0.93, context precision 1.0 on 3 of 5. These checks are lexical and cannot see if an answer is
right. Read by hand, answers can rest on ended law (Decree 123/2008, Law 13/2008, Circular 32/2011) and
can mislabel a document's type ("Nghị định 68/2019/TT-BTC", which is a circular). Both models were read
only briefly, so quality was not compared.

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
| Hybrid baseline | About 3.5 minutes (6-9 before 23/11/2026) | None |
| Issue-guided baseline | 8-23 minutes | None |
| `freeze_corpus.py` | 30 s | None |
| `extract_repeals.py` | 100 s | None |
| 5 answer questions | About 6 minutes | About $0.01 |
| Full collection build, 10 rounds of 100 | 13.7 hours | None |
| OCR, embedding | About 2.5 s a page, 0.3 s a passage | None |

Why a hybrid baseline takes longer than an answer's 3-6 s of retrieval (measured 23/11/2026): about 35 s
once per run (model load 21 s, corpus check 12 s), then per question keyword search 1.5-5 s and vector
search 2-10 s. Each round trip from a laptop costs about 0.2 s, against about 1 ms inside Azure, and the
1-vCore, 2 GB database answers the same query in 2-10 s depending on its cache. Its CPU credits stayed
full, so it is not throttled. Running evaluations inside Azure would save the round trips only.

**Things that wasted runs:** Windows carriage returns in `az` output in Git Bash (use `tr -d '\r'`), a laptop IP change (check `curl https://api.ipify.org` against the
firewall first), internet drops (runs start over, so use a steady connection), and short `timeout`
values that killed a run and lost its output. A missing `AZURE_STORAGE_CONNECTION_STRING` (set it with
the database settings; [operations](operations.md#laptop-access-to-azure)): until 23/11/2026 the report was
uploaded before it was saved, so the failed upload lost an 8-minute run. It is now saved first.
