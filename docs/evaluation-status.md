# Status

Where TaxLens stands as of 23/11/2026. Rewritten as things change. What has been tried is in
[retrieval-experiments.md](retrieval-experiments.md): read it before running anything.

## What is live

- **Site:** `aa3c86a`, released 23/11/2026, answering with `openai/gpt-oss-120b`. Answers leave out
  documents whose end is confirmed and flag inferred endings ([ended documents](retrieval.md#ended-documents)):
  the `corpus-v2` list (rebuilt after the rule fix of item 3) is loaded, leaving out 711 documents and
  flagging 124 as of 23/11/2026. Checked on the 5 answer questions against the live database, and the
  tags by eye in the app ("Ended 01/07/2022 · by 78/2021/TT-BTC"; no "In force" beside them).
- **Corpus:** `corpus-v2.1`, frozen 23/11/2026: 2,986 documents, 2,986 versions, 144,279 passages, all
  embedded. `corpus-v2` with 14 duplicates merged; recall is identical on all three baselines.
- **Access:** Tri, and Le Hung as a collaborator ([what each can reach](operations.md#access)).
- **Airflow:** stopped. Keep it stopped, and the daily DAG paused, or the frozen corpus changes.
- **Speed:** a warm answer takes about 5.5 s inside Azure: retrieval 4.0 s (keyword 3.1 s, vector
  0.8 s) and the model 1.6 s, as the API now logs per request. The first question after 5 idle minutes
  waits for the API to start: image pull 13 s, then startup and model load.

## Results

Essential recall on `corpus-v2`, 12 gold cases, full coverage in brackets where not 0. Too few cases
to separate most methods.

| Method | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| Keyword | 0.22 (0.08) | 0.30 (0.25) | 0.42 (0.25) |
| Hybrid (what the site does) | 0.10 | 0.30 (0.08) | 0.41 (0.25) |
| **Hybrid + filter for ended documents** | **0.35 (0.17)** | **0.45 (0.25)** | **0.45 (0.25)** |
| Hybrid + cautious filter (explicit repeals and ministry dates only) | 0.31 (0.08) | 0.42 (0.25) | 0.45 (0.25) |
| Issue-guided | 0.04 | 0.10 | 0.15 |

On `corpus-v1.2`, with TCVN3 unconverted: hybrid 0.30, 0.41, 0.45; with filter 0.38, 0.45, 0.45.

**What these mean.** Adding documents lowered recall because old, ended documents crowd the top: new
documents took 25-28% of the top 10. The filter restores it, but rests on 12 cases, was built after
seeing the problem, and includes rules no legal expert has validated. The cautious filter needs no
inferred rules and gets most of the gain (against no filter, K = 10: 4 cases up, 1 down, p = 0.38); it
trails the full filter by one provision at K = 5 and one at K = 10 (A1 ranks 11th instead of 10th). Neither
filter removes a gold document. The TCVN3 repair and appendix labels changed in the same step, and their
effect was not separated.

## Answers

The 16 gold questions answered as the site answers them on 23/11/2026, graded against the gold answers
by `Qwen/Qwen3-235B-A22B-Instruct-2507` and read by hand (`answers-gold-v1-2026-11-23.json`, which
records where the reader differs). Of 15 counted cases (L1 is uncertain):

| Judge | Correct | Partly | Wrong | Refused |
| --- | --- | --- | --- | --- |
| Model | 9 | 1 | 3 | 2 |
| Reader | 8 | 2 | 3 | 2 |

Wrong: A7 and L2 apply today's rule to 2023-2024 facts; A9 rests on a 1998 circular. Refused: A1, where
all 5 passages were old documents without locators, and R2. Neither grader is a tax expert.

After items 6 and 7 (`answers-gold-v1-2026-11-23b.json`): still 9 of 15 by the judge. L2 is now correct.
R1 and A4 got worse with the same evidence, so the model's conclusions vary between runs; with 15 cases a
score can move by two without any change. A1 has current law among its passages but refuses, since the
VAT-reduction decree is not retrieved.

## Corpora

Manifests are in `data/evaluation/corpus/`. Runs against an older corpus stop at the corpus check.

| Corpus | What it is | Documents | Passages | Fingerprint |
| --- | --- | --- | --- | --- |
| `corpus-v1` | Original | 2,026 | 61,208 | `317f5a0d` |
| `corpus-v1.1` | 8 PDFs repaired | 2,026 | 61,204 | `cd396fa3` |
| `corpus-v1.2` | Circulars 80/2021 and 25/2018 added | 2,028 | 62,182 | `7df84879` |
| `corpus-v2` | [Rules](corpus-inclusion.md), TCVN3 repaired, 41 numbers corrected | 2,991 | 144,600 | `62b499cf` |
| **`corpus-v2.1`** | 14 duplicates merged ([plan](../data/evaluation/corpus/merge-duplicates-v2.1.json)), date of 124/2026 set | 2,986 | 144,279 | `07175db6` |

## Known problems

1. **Ended law the list does not know.** Answers no longer use Law 13/2008, Circular 32/2011, Circular
   68/2019 or Decree 119/2018, and flag Decree 123/2008. A document still ends only if the corpus or the
   ministry says so, and the rules read lists by their first number per item (`ø) Thông tư 19/2021 và
   Thông tư 46/2024` ends only 19/2021).
2. **Most essential provisions are still missed.** About half of the hardest need a legal step the
   question does not state ([diagnosis](retrieval-experiments.md#retrieval)).
3. **Answer model trade-offs:** the faster model costs about $0.002 an answer, against $0.0003, and can
   mislabel a document's type. It depends on Groq and Cerebras staying on the router.
4. **Answers are right on 9 of 15 gold questions** (judge model, read by hand; [Answers](#answers)).
   Dated questions and unlocated old documents are handled since `f0f72b6`; what remains is evidence that
   is not retrieved (A1, A4, A9), and run-to-run variation of the model's conclusion.
5. **Duplicates merged in `corpus-v2.1`:** 14 numbers held two copies; the better one stays under the clean
   number and the other is backed up in `removed-duplicates-v2.1.json`. 17 other numbers keep stray spaces
   but have no twin.
6. **Numbers still uncertain:** `93/1998/QĐ/TCKT`, whose header reads `91/1998/QĐ-BNN-BVTV` (wrong number
   on the portal, or the wrong file), and `25/2026/TT-BTC`, whose OCR'd header reads `85/2026`; neither is
   found online. `124/2026/TT-BTC` is confirmed (dated 22/08/2026 by LuatVietnam). The other 50 flags in the
   library are OCR misreads, shortened headers, or citations picked up as headers.
7. **Failed or absent:** 9 documents have no text (7 Excel workbooks filed as `.rtf`, a 2-byte file,
   `204/2004/NĐ-CP`). `56/2009/NĐ-CP` (invalid file on the portal) and `38/2015/TT-BTC` (download failed)
   were not collected. Originals of some amendments, such as `68/2025` and `83/2024/TT-BTC`, are not
   held.
8. **Small text issues:** `191/2010/TT-BTC` keeps split syllables; words like `cã` can stay
   unconverted in mixed-font lines; mislabelled numbers can recur, since collection trusts the listing
   and only flags a mismatch.

## To do

Ranked by worth for the effort, done one at a time from the top. Effort: S = hours, M = a day or two,
L = more. Mark each done here when finished.

| # | Task | Effort | Why |
| --- | --- | --- | --- |
| ~~1~~ | **Done 23/11/2026.** Cautious filter on `corpus-v2`: 0.31, 0.42, 0.45, against 0.35, 0.45, 0.45 for all rules | | See [Results](#results) |
| ~~2~~ | **Done 23/11/2026,** released in `2669c02`: confirmed endings left out of answers, inferred ones flagged, tags in the app | | [Ended documents](retrieval.md#ended-documents) |
| ~~3~~ | **Done 23/11/2026.** Lists split across passages, items after OCR page numbers, and "continues in force until" clauses are read; 29 more documents end, loaded on Azure. Recall unchanged | | [Already tried](retrieval-experiments.md#retrieval) |
| ~~4~~ | **Done 23/11/2026.** Evaluation runs about 30% faster (TensorFlow no longer loaded, one count query per case); the rest is laptop round trips and a small database. Answers are not slowed by the new filter | | [Speed](retrieval-experiments.md#speed) |
| ~~5~~ | **Done 23/11/2026.** `grade_answers.py`: 9 of 15 correct by the judge, 8 by the reader | | [Answers](#answers) |
| ~~6~~ | **Done 23/11/2026,** released in `f0f72b6`: evidence is the first 5 located passages of 20. A1 now gets current law, and still refuses: the VAT-reduction decree is not retrieved | | [Answers](#answers) |
| ~~7~~ | **Done 23/11/2026,** released in `f0f72b6`: answers use the period a question names. L2 now correct. Filtered searches resolve versions first (vector 10 s → 1.3 s) | | [Answers](#answers) |
| ~~8~~ | **Done 23/11/2026,** released in `9f26f28`: the image holds only `model.safetensors`; 1.92 → 0.77 GB, image pull 35 s → 13 s on each cold start | | [Speed](retrieval-experiments.md#speed) |
| ~~9~~ | **Done 23/11/2026.** Keyword search without a parallel worker on the 1-vCore database: 3.4 → 2.4 s, identical results. What remains is grouping about 750,000 term matches; faster needs an approximate method (with an evaluation) or a larger database | | [Speed](retrieval-experiments.md#speed) |
| 10 | Keep the API warm longer after use: `cooldown_period_in_seconds = 1800` in the API template (`infra/terraform/main.tf`, default 300). An idle API replica (1 vCPU, 2 GiB) costs $0.000009 a second in East Asia, $0.032 an hour (retail price list, 23/11/2026): at most $0.016 per use, about $1 a month at two uses a day | S, **waiting for the owner** (cost) | The first question after 5 idle minutes waits for the API to start |
| ~~11~~ | **Done 23/11/2026.** Questions, answers, and timings are logged in `question_logs`, and answers can be rated 👍/👎 with a comment; `export_question_log.py` lists rated and refused ones for review | | [Architecture](architecture.md) |
| 12 | **Drafts ready, review waiting:** 18 cases in `gold_set_v1_drafts.csv` (CIT rates, PIT deductions and household business, late-payment interest, invoice timing, 0% VAT conditions, refund cap, a false premise, 3 leakage-free), each from the clause text and checked to parse. Hung or an expert must verify them before they count; then draft 16 more | M for drafts, L for review | 12 scored cases cannot separate methods or test the filter independently |
| ~~13~~ | **Done 23/11/2026.** 14 duplicates merged by `merge_duplicate_documents.py` (321 passages removed, backed up), `corpus-v2.1` frozen, ended-document list rebuilt and loaded, baselines identical; 124/2026 confirmed, 2 numbers left for someone with the originals | | [Corpora](#corpora) |
| ~~14~~ | **Done 23/11/2026.** ESLint 9 with Next's `core-web-vitals` and `typescript` rules (`eslint.config.mjs`); CI runs `npm run lint` and `next build` lints too. Fixed 2 errors (page links in the admin view); 3 warnings remain (two `<img>` logos, one effect's dependency list) | | |
| 15 | Try a reranker over the top 100 (e.g. `bge-reranker-v2-m3`) | M, **waits for item 12's reviewed cases** | Weak top-5 recall; cannot reach the 14 never-found provisions |
| 16 | Step that works out which law a question depends on, as its own lower-weight list in fusion | L, **waits for item 12's reviewed cases** | Half the hardest misses need it |
| ~~17~~ | **Done 23/11/2026.** `page.tsx` (890 lines) split without code changes into `lib/` (types, copy, format, api) and `components/` (tags, answer, documents, layout); 12 Vitest tests for the helpers and tags run in CI (`npm test`) | | |

**For people, not code:** a tax expert reviews the filter's inferred rules and the 178 documents the
ministry says are in force but our list ends; tell the professor that all earlier results had the TCVN3
bug (hybrid fell from 0.41 to 0.30 before the filter brought it to 0.45); the owner removes stale
database firewall rules (old images are cleared; leave `CreditScorecardWOEIV`, which serves another
project); install `gh` on the laptop; delete the merged local branches.
