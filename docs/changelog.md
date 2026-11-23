# Changelog

What each working stint changed, newest first. Current state and the to-do list are in
[evaluation-status.md](evaluation-status.md); every measurement is in
[retrieval-experiments.md](retrieval-experiments.md).

## 23/11/2026

Live: code `e32fe74`, corpus `corpus-v2.1`. To-do items 1-11, 13, 14, and 17 done;
item 12 drafted and waiting for review; items 15-16 wait on it.

### For people using TaxLens

- **Ended law.** Answers leave out documents that a later document repeals or that the Ministry of
  Finance records as expired (711 today), and flag 123 that may have ended by inference
  ([ended documents](retrieval.md#ended-documents)). Answers no longer rest on Law 13/2008,
  Circular 32/2011, Circular 68/2019, or Decree 119/2018.
- **Dated questions** ("Tháng 6/2023") are answered with the law of that period. Gold case L2 went from
  wrong to correct.
- **Evidence** is the first 5 passages with an article or page, of 20, so old documents without articles
  no longer crowd out current law.
- **Feedback.** Answers can be rated 👍/👎 with a comment; questions, answers, and timings are logged in
  `question_logs`.
- **Tags** in citations, search, and the library: "Ended 01/07/2022 · by 78/2021/TT-BTC" or "May have
  ended …", in English and Vietnamese; "In force" is no longer shown beside a passed ending.

### Speed

| | Before | After |
| --- | --- | --- |
| Warm answer to a dated question | 62 s at worst | about 5 s |
| Image pull at cold start | 35 s (1.92 GB) | 13 s (0.77 GB) |
| Keyword search, 29-term question | 11 s | 2.4 s |
| Retrieval evaluation run | about 4.5 min | about 3.2 min |
| API scale-to-zero after idle | 5 min | 10 min (owner's choice) |

Causes found by measuring, not guessing: filters joined into the passage scans led to bad plans (now the
versions a filter keeps are read first); a parallel worker on the 1-vCore database; the image held the
embedding model four times; TensorFlow loaded with the model on laptops.

### Quality and evaluation

- `grade_answers.py` grades the site's answers against the gold answers: 9 of 15 by the judge model,
  8 when read by hand ([answers](evaluation-status.md#answers)).
- Cautious ended-document filter on the 12 gold cases: recall 0.31, 0.42, 0.45 at K = 5, 10, 20, against
  0.10, 0.30, 0.41 without.
- The explicit repeal rule now reads lists split across passages and "tiếp tục có hiệu lực đến ngày"
  clauses: 29 more documents end.
- `corpus-v2.1`: 14 duplicated documents merged by a reviewed plan, with a backup of what was removed;
  recall unchanged. 124/2026/TT-BTC confirmed and dated.
- 18 draft gold cases from the clause text in `gold_set_v1_drafts.csv`, unverified and not scored.

### UI and accessibility

Audited against the Vercel web interface guidelines and the ui-ux-pro-max accessibility rules, then
checked in the live app at desktop and phone widths, in both languages, and by keyboard:

- Visible 3px focus ring on every control, and a ring around the search and question boxes; a skip link.
- Muted text contrast 3.8:1 → 5.2:1 (WCAG AA needs 4.5:1).
- The page's `lang` follows EN/VI; language buttons report which is selected; tabs mark the current view;
  search inputs are named; one polite status line announces "10 matching passages" or that an answer is
  ready.
- SVG icons instead of glyphs and emoji; 44px touch targets on touch screens; the top bar stays on one
  line at 375px.
- Be Vietnam Pro and Source Serif 4, self-hosted with the Vietnamese subset: Vietnamese now uses the
  same typefaces as English instead of falling back to Arial (Inter was named but never loaded).
- Login and admin forms post, so a submit before the page script loads never puts a password in the URL
  (found by the automated security review).

### Engineering

- Each answer logs its timings (version list, keyword and vector queries, model, tokens) in the API logs.
- Web: `page.tsx` split into `lib/` and `components/` without code changes; ESLint and 14 Vitest tests run
  in CI. Backend tests 113 → 189.
- Security: both CSV exports guard against formula injection (found by the automated review).
- Releases run from the GitHub CLI; a settings-only release skips the image build.

### Known problems fixed (later the same day)

- **Ended law.** A run of replaced documents ("thay thế các Thông tư số X …, Y … và Z") now ends each
  of them; 33 more documents end and 14 guesses are confirmed (729 left out today, 127 flagged). Gold
  recall unchanged with confirmed rules; 0.38 at K = 5 with all rules, the best yet.
- **Old guidance in answers.** Documents that may have ended by the question's date are used only
  when too few others are found, and the model may not call a document in force after its ending.
  Gold answers: wrong 4 → 2, refused 2 → 5, correct 9 → 8.
- **Tried and dropped:** ranking newer documents higher. It lifted old circulars with no recorded
  ending as much as current law.
- Numbers with spaces (`101 TC/TCT`, `18/VBHN-BTC (2026)`) are how those documents are numbered, not
  errors.

### Documentation

- README rewritten around what TaxLens is for, with current results, features, and new screenshots.
- [architecture.md](architecture.md) rewritten: how a question is answered, the question log, logging,
  delivery, and the decisions taken this stint. Retrieval, operations, and pipeline docs brought up to date.

### Incidents

- An 8-minute evaluation run was lost because the report was uploaded before it was saved; it now saves
  first.
- One push failed CI after a signature change tested only in part; the full suite now runs before pushes.
- One release failed at Azure sign-in (transient); the retry passed.
- Polling CI through the unauthenticated GitHub API hit its hourly limit; the GitHub CLI is used instead.

### Cost

A few US cents in model calls (three grading runs, a handful of live questions). Evaluations and database
work are free. Releases and CI stay inside the free GitHub Actions minutes. The 10-minute cooldown adds at
most about $0.005 per use.
