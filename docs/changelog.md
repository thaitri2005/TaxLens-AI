# Changelog

What each working stint changed, newest first. Current state and the to-do list are in
[evaluation-status.md](evaluation-status.md); every measurement is in
[retrieval-experiments.md](retrieval-experiments.md).

## 24/11/2026

- **Oracle issue experiment** (Prof. Thanh's suggestion), draft queries pending Le Hung's review: told
  the right legal issue, search finds only 25% of the missed provisions in the top 10. Retrieval, not
  naming the issue, is the bottleneck; superseded law outranked current law
  ([results](../data/evaluation/oracle/results.md)).
- **Item 19:** 30 more endings read from the corpus (lists after a colon, lists of replaced laws, laws
  ending as amended), loaded on Azure: 753 documents left out, 119 flagged. Recall identical; oracle
  25% → 28% at K = 10. The rest of the old law in the way has no ending stated in the corpus.

## 23/11/2026 (stint report)

Live: release `7662082` (code as of `e32fe74`), corpus `corpus-v2.1`, endings list rebuilt 23/11/2026.
To-do items 1-15, 17, and 18 done or decided; item 16 is next.

### Conclusion

1. **The site is now fast, careful about ended law, and accessible.** A warm answer takes about 5.5 s
   instead of up to 62 s. Answers leave out 729 ended documents and use the 127 that may have ended only
   as a last resort. Dated questions get the law of their date. The interface works by keyboard, screen
   reader, and phone in both languages.
2. **Finding the right provision is what limits quality.** On 30 scored gold cases, 31% of the essential
   provisions are in the top 5 passages and 53% in the top 20. Answers to the first 15 questions: 8
   correct, 2 wrong, 5 refused. Most wrong or refused answers traced so far lacked the governing
   provision in their evidence; one (A7) applied today's rule to earlier facts.
3. **Ranking tricks do not fix it.** Tried and measured: more candidates, rare-term weighting, issue
   decomposition, newest-first ranking, and two cross-encoder rerankers. None raised the top 5 or 10.
   About half of the misses need a legal step the question never states (which law decides a refund,
   which decree sets a rate), so the next lever is item 16: work out the governing law first and search
   for it as its own list.
4. **Two things only people can unlock.** A tax expert validating the inferred ending rules would let the
   all-rules filter go live (0.37 instead of 0.31 at K = 5, no case worse). 16 more gold cases would
   reach 50 and separate methods more reliably.
5. **Cost** stayed under $0.20 in model calls for the whole stint; everything else ran on the laptop or
   inside free CI minutes.

### For people using TaxLens

- **Ended law.** Answers leave out documents that a later document repeals or the Ministry of Finance
  records as expired (729 today), and use the 127 that may have ended by inference only when too few
  others are found. Runs of replaced documents ("thay thế các Thông tư số X …, Y … và Z") are now read.
  Answers no longer rest on Law 13/2008, Circulars 32/2011 and 68/2019, or Decrees 119/2018 and 123/2008.
- **Dated questions** ("Tháng 6/2023") are answered with the law of that period, and the model may not
  call a document in force after its ending. The 2017 export-refund question now cites 219/2013.
- **Evidence** is the first 5 passages with an article or page, of 20, so old documents without articles
  no longer crowd out current law.
- **Feedback.** Answers can be rated 👍/👎 with a comment; questions, answers, and timings are logged in
  `question_logs`.
- **Tags** in citations, search, and the library: "Ended 01/07/2022 · by 78/2021/TT-BTC" or "May have
  ended …"; source names in full ("Official Gazette").

### Speed

| | Before | After |
| --- | --- | --- |
| Warm answer to a dated question | 62 s at worst | about 5.5 s |
| Image pull at cold start | 35 s (1.92 GB) | 13 s (0.77 GB) |
| Keyword search, 29-term question | 11 s | 2.4 s |
| Retrieval evaluation run (12 cases) | about 4.5 min | about 3.2 min |
| API scale-to-zero after idle | 5 min | 10 min (owner's choice) |

Causes found by measuring, not guessing: filters joined into the passage scans led to bad plans (now the
versions a filter keeps are read first); a parallel worker on the 1-vCore database; the image held the
embedding model four times; TensorFlow loaded with the model on laptops.

### Quality and evaluation

| Measure | Start of stint | End of stint |
| --- | --- | --- |
| Gold cases (scored) | 16 (12) | 34 (30); the 18 new ones reviewed and approved by the owner |
| Essential recall, top 5 / 10 / 20, as live | 0.10 / 0.30 / 0.41 (12 cases, no filter) | 0.31 / 0.47 / 0.53 (30 cases) |
| Same, all ending rules | 0.35 / 0.45 / 0.45 (12) | 0.37 / 0.45 / 0.53 (30) |
| Answers to 15 gold questions | not graded | 8 correct, 2 wrong, 5 refused |

- `grade_answers.py` grades the site's answers against the gold answers with a judge model from another
  family; the first run's grades were all read by hand.
- `corpus-v2.1`: 14 duplicated documents merged by a reviewed plan, with a backup; 124/2026/TT-BTC
  confirmed and dated.
- The endings list grew to 859 entries; each new explicit ending was read against its source sentence.
- **Tried and rejected** ([already tried](retrieval-experiments.md)): newest-first ranking (it lifted old
  circulars with no recorded ending as much as new law); `bge-reranker-v2-m3` over the top 100 (0.31,
  0.43, 0.58: reaches four never-found provisions at K = 20 but loses reworded cases, and would take
  about 110 s a question on the site's CPU); a small multilingual reranker (worse alone and fused).

### UI and accessibility

Audited against the Vercel web interface guidelines and the ui-ux-pro-max accessibility rules, then
checked in the live app at desktop and phone widths, in both languages, and by keyboard:

- Visible 3px focus ring on every control, and a ring around the search and question boxes; a skip link.
- Muted text contrast 3.8:1 → 5.2:1 (WCAG AA needs 4.5:1).
- The page's `lang` follows EN/VI; language buttons report which is selected; tabs mark the current view;
  search inputs are named; one polite status line announces results.
- SVG icons instead of glyphs and emoji; 44px touch targets on touch screens; the top bar stays on one
  line at 375px.
- Be Vietnam Pro and Source Serif 4, self-hosted with the Vietnamese subset (Inter was named but never
  loaded, so Vietnamese fell back to Arial).
- Login and admin forms post, so a submit before the page script loads never puts a password in the URL.

### Engineering

- Each answer logs its timings, and how many chosen passages may have ended.
- Web: `page.tsx` split into `lib/` and `components/`; ESLint and 14 Vitest tests run in CI. Backend
  tests 113 → 194.
- Security: CSV exports guard against formula injection (found by the automated review).
- Releases run from the GitHub CLI; a settings-only release skips the image build.
- The retrieval evaluation can test any cross-encoder (`--reranker`, `--rerank-fuse`, `--rerank-cache`).

### Documentation

- README rewritten around what TaxLens is for, with current results and new screenshots.
- [architecture.md](architecture.md) rewritten; retrieval, operations, pipeline, status, and the
  experiment record kept current with every change.

### Incidents

- An 8-minute evaluation run was lost because the report was uploaded before it was saved; it now saves
  first.
- One push failed CI after a signature change tested only in part; the full suite now runs before pushes.
- One release failed at Azure sign-in (transient); the retry passed.
- Polling CI through the unauthenticated GitHub API hit its hourly limit; the GitHub CLI is used instead.
- One evaluation ran with the script's default (all ending rules) instead of the live setting; it was
  kept as the all-rules figure and rerun.

### Cost

Under $0.20 in model calls (three grading runs, a few live questions). Evaluations, the reranker trial,
and database work ran on the laptop for free; releases and CI stay inside the free GitHub Actions minutes.
The 10-minute cooldown adds at most about $0.005 per use.
