# Status

Where TaxLens stands as of 23/11/2026. Rewritten as things change. What has been tried is in
[retrieval-experiments.md](retrieval-experiments.md): read it before running anything. What each stint
changed is in [changelog.md](changelog.md).

## What is live

- **Site:** `76bfdfa`, released 23/11/2026 (questions logged and rated, keyword search 30% faster, the
  accessible interface in both languages), answering with `openai/gpt-oss-120b`. Answers leave out
  documents whose end is confirmed and flag inferred endings ([ended documents](retrieval.md#ended-documents)):
  the `corpus-v2.1` list (rebuilt 23/11/2026 to read runs of replaced documents) is loaded, leaving out
  729 documents and flagging 127 as of 23/11/2026. Checked on the 5 answer questions against the live database, and the
  tags by eye in the app ("Ended 01/07/2022 · by 78/2021/TT-BTC"; no "In force" beside them).
- **Corpus:** `corpus-v2.1`, frozen 23/11/2026: 2,986 documents, 2,986 versions, 144,279 passages, all
  embedded. `corpus-v2` with 14 duplicates merged; recall is identical on all three baselines.
- **Access:** Tri, and Le Hung as a collaborator ([what each can reach](operations.md#access)).
- **Airflow:** stopped. Keep it stopped, and the daily DAG paused, or the frozen corpus changes.
- **Speed:** a warm answer takes about 5.5 s inside Azure: retrieval 4.0 s (keyword 3.1 s, vector
  0.8 s) and the model 1.6 s, as the API now logs per request. The first question after 10 idle minutes
  waits for the API to start: image pull 13 s, then startup and model load.

## Results

**34 cases since 23/11/2026** (18 reviewed drafts added, `d568800`; 30 with essential provisions),
`corpus-v2.1`, full coverage in brackets:

| Method | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| **Hybrid + cautious filter (what the site does)** | **0.31 (0.20)** | **0.47 (0.37)** | **0.53 (0.43)** |
| Hybrid + filter, all rules | 0.37 (0.27) | 0.45 (0.33) | 0.53 (0.43) |

The first 12 cases score as before; the 18 new ones 0.31, 0.50, 0.58. All rules against cautious: K = 5,
3 cases up (A7, A8, A13), none down; K = 10, A1 up and A18 down. Never found in the top 20: CIT Law
67/2025 Art 10 (A10, A11, R4), Tax Administration Law 108/2025 Art 16 (A15, A16), Decree 181/2025 Art
18 and 26 (A20, A22). Reports `hybrid-asof-*-v2.1-gold34`.

Earlier, on `corpus-v2`, 12 gold cases, full coverage in brackets where not 0. Too few cases
to separate most methods.

| Method | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| Keyword | 0.22 (0.08) | 0.30 (0.25) | 0.42 (0.25) |
| Hybrid (what the site does) | 0.10 | 0.30 (0.08) | 0.41 (0.25) |
| **Hybrid + filter for ended documents** | **0.35 (0.17)** | **0.45 (0.25)** | **0.45 (0.25)** |
| Hybrid + cautious filter (explicit repeals and ministry dates only) | 0.31 (0.08) | 0.42 (0.25) | 0.45 (0.25) |
| Hybrid + filter, all rules, `corpus-v2.1` list with runs read | 0.38 | 0.45 | 0.45 |
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

With documents that may have ended used last (`answers-gold-v1-2026-11-23c.json`, `e32fe74`): 8 correct,
2 wrong, 5 refused, against 9, 4, 2. A4 and A9 refuse instead of answering wrongly. A6 refuses: its earlier
correct answer rested on `26/2015/TT-BTC`, which guides a decree replaced on 15/12/2025, and the current
rule is not retrieved. A wrong answer is worse than a refusal in a legal tool, so this is live.

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

1. **Ended law the list does not know.** A document ends only if the corpus or the ministry says so.
   Runs of replaced documents (`thay thế các Thông tư số X …, Y … và Z`) are read since `8829e78`, which
   ended 33 more (59/2007, 79/2000, 26/2009, 45/2014 …) and confirmed 14 guesses, Decree 123/2008 among
   them. Still unknown when the replacing document is not held: 194/2010/TT-BTC, replaced by 128/2013,
   stays in force for the site.
2. **Most essential provisions are still missed.** About half of the hardest need a legal step the
   question does not state ([diagnosis](retrieval-experiments.md#retrieval)).
3. **Answer model trade-offs:** the faster model costs about $0.002 an answer, against $0.0003, and can
   mislabel a document's type. It depends on Groq and Cerebras staying on the router.
4. **Answers are right on 8 of 15 gold questions, wrong on 2, refused on 5** (judge model;
   [Answers](#answers)). What remains is evidence that is not retrieved (A1, A4, A6, A9), and run-to-run
   variation of the model's conclusion.
5. **Duplicates merged in `corpus-v2.1`:** 14 numbers held two copies; the better one stays under the clean
   number and the other is backed up in `removed-duplicates-v2.1.json`. The 17 numbers with spaces are
   written so on purpose: 1990s ministry numbers (`101 TC/TCT`) and consolidated texts told apart by year
   (`18/VBHN-BTC (2026)`).
6. **Numbers still uncertain:** `93/1998/QĐ/TCKT`, whose header reads `91/1998/QĐ-BNN-BVTV` (wrong number
   on the portal, or the wrong file), and `25/2026/TT-BTC`, whose OCR'd header reads `85/2026`; neither is
   found online. `124/2026/TT-BTC` is confirmed (dated 22/08/2026 by LuatVietnam). The other 50 flags in the
   library are OCR misreads, shortened headers, or citations picked up as headers.
7. **Failed or absent:** 9 documents have no text (7 Excel workbooks filed as `.rtf`, a 2-byte file,
   `204/2004/NĐ-CP`). `56/2009/NĐ-CP` (invalid file on the portal) and `38/2015/TT-BTC` (download failed)
   were not collected. Originals of some amendments, such as `68/2025` and `83/2024/TT-BTC`, are not
   held.
8. **Old guidance could outrank current law** (seen on the live site, 23/11/2026). Asked when exporters
   get a VAT refund, undated, the answer cited only 2009-2018 circulars flagged "may have ended"; asked
   about 2017, it called `4/2009/TT-BTC` (flagged as ended in 2009) in force. Since `e32fe74`, documents
   that may have ended by the question's date fill the evidence only after the others, and the prompt
   forbids calling a document in force after its ending. Current law for the undated question (VAT Law
   48/2024, rank 34) is still not retrieved: that is problem 2.
9. **Small text issues:** `191/2010/TT-BTC` keeps split syllables; words like `cã` can stay
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
| ~~10~~ | **Done 23/11/2026** (owner's choice: 10 minutes): the API stays up 10 idle minutes instead of 5 (`cooldown_period_in_seconds = 600`, `infra/terraform/main.tf`), about $0.005 more per use | | |
| ~~11~~ | **Done 23/11/2026.** Questions, answers, and timings are logged in `question_logs`, and answers can be rated 👍/👎 with a comment; `export_question_log.py` lists rated and refused ones for review | | [Architecture](architecture.md) |
| ~~12~~ | **Done 23/11/2026.** The 18 drafts, reviewed and approved by the owner, are A10-A23, R4-R5, L5-L6 (`d568800`); 30 scored cases. Drafting 16 more would bring the set to 50 | | [Results](#results) |
| ~~13~~ | **Done 23/11/2026.** 14 duplicates merged by `merge_duplicate_documents.py` (321 passages removed, backed up), `corpus-v2.1` frozen, ended-document list rebuilt and loaded, baselines identical; 124/2026 confirmed, 2 numbers left for someone with the originals | | [Corpora](#corpora) |
| ~~14~~ | **Done 23/11/2026.** ESLint 9 with Next's `core-web-vitals` and `typescript` rules (`eslint.config.mjs`); CI runs `npm run lint` and `next build` lints too. Fixed 2 errors (page links in the admin view); 3 warnings remain (two `<img>` logos, one effect's dependency list) | | |
| ~~15~~ | **Tried 23/11/2026, rejected.** Cross-encoders over the top 100: `bge-reranker-v2-m3` 0.31, 0.43, 0.58 (reaches 4 never-found provisions at K = 20 but loses the reworded cases, and needs about 110 s a question on the site's CPU); a small multilingual one is worse alone or fused. `--reranker` stays in the evaluation for later models | | [Already tried](retrieval-experiments.md#retrieval) |
| 16 | Step that works out which law a question depends on, as its own lower-weight list in fusion | L, **on hold** | The oracle (draft) shows that even a named issue recovers only 25% at K = 10: superseded law must be kept out first ([results](../data/evaluation/oracle/results.md)) |
| 19 | Extend the endings list to old documents replaced by later ones on the same subject (158/2003, 07/2003, 129/2013 …), then rerun the oracle | M | The oracle's main failure |
| ~~17~~ | **Done 23/11/2026.** `page.tsx` (890 lines) split without code changes into `lib/` (types, copy, format, api) and `components/` (tags, answer, documents, layout); 12 Vitest tests for the helpers and tags run in CI (`npm test`) | | |
| ~~18~~ | **Done 23/11/2026.** Known problems 1 and 8: runs of replaced documents read (33 more ended, recall with confirmed rules identical case by case, all rules 0.38 at K = 5), and documents that may have ended used last in answers (wrong 4 → 2, refused 2 → 5). A newest-first ranking was tried and rejected | | [Already tried](retrieval-experiments.md#retrieval) |

### For people, not code

Waiting on a person (23/11/2026); code items above that depend on one say so.

1. **Review the 30 oracle queries** in `data/evaluation/oracle/oracle-queries.json` (Le Hung) against the
   rules in its plan; the oracle result counts only after it.
2. ~~Review the 18 draft gold cases~~ **done 23/11/2026** by the owner. A tax expert's second reading would
   still strengthen them, and 16 more cases would reach 50.
2. **Check two document numbers against the originals:** `93/1998/QĐ/TCKT` (its header reads
   `91/1998/QĐ-BNN-BVTV`) and `25/2026/TT-BTC` (its OCR'd header reads `85/2026`).
3. **Tax expert:** review the inferred ending rules (guidance, amendment) and the 178 documents the
   ministry says are in force but our list ends.
4. **Tell the professor:** all earlier results had the TCVN3 bug (hybrid fell from 0.41 to 0.30 before the
   filter brought it to 0.45).
5. **Azure (owner):** remove stale database firewall rules. Old images are cleared; leave
   `CreditScorecardWOEIV`, which serves another project.
6. **Owner's laptop:** the user `Path` has entries joined by spaces instead of separate lines, which hides
   `winget`, Terraform, and others from shells.
