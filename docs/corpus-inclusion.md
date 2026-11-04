# Corpus inclusion rules for corpus-v2

Written before any candidate list was made, and without reading the gold set for
documents to add. `corpus-v1` closed its gaps with `collect_sources.py --cited-by`, which
collects what the gold set cites: those documents enter because they are the answers, and
a non-tax law then has no similar documents around it. These rules replace that step.

**Where this stands:** `corpus-v2` is selected but not collected. The selection is 975 new
documents (420 `C2`, 251 `C3`, 304 `C4`), about 66,000 passages and 20 hours of processing.
Dated sections below are in the order the work was done, so later ones correct earlier
counts. The corpora and results so far are summarized in
[evaluation-status.md](evaluation-status.md).

## Rules

A document enters `corpus-v2` if it is national and normative (a law, resolution of the
National Assembly, decree, or circular, not a provincial document or official letter) and
meets one rule. Each document records the first rule it met.

| Rule | What it admits | Why |
| --- | --- | --- |
| `C1 tax` | Everything `corpus-v1` collected by subject: the portal's tax category, the ministry's tax selection | The existing corpus |
| `C2 tax title` | Any portal category, if `is_tax_title` accepts the title | The portal does not file every tax document under tax (Decree 181/2025) |
| `C3 cited` | Cited by number in the operative text of at least 2 different tax documents that had not ended on the freeze date | A rule that tax documents apply is part of tax law, whatever its subject |
| `C4 any law` | Every law (`Luật`) of the National Assembly in force on the freeze date, on any subject | Tax rules use categories that other laws define, often without citing them. Taking all laws avoids choosing sectors by hand and brings unrelated laws along, so a non-tax law is not trivially easy to find |

Details fixed now:

- Enacting clauses ("Căn cứ ...") do not count as citations, because they name a document's
  legal basis, not the rule it applies.
- "Had not ended" uses `data/evaluation/repeals/corpus-v1.json`, all rules.
- The threshold of 2 is not tuned. A sensitivity count at 1 and 3 is reported, without
  changing the rule.
- Documents admitted only for `corpus-v1`'s gold set stay out unless a rule admits them.
  `gold_supplement.json` (Circulars 80/2021 and 25/2018) is removed from the plan unless
  `C3` admits them and an official file can be found.

## What is reported

For every gold essential provision, one of: `in corpus (rule)`, or `coverage failure`. A
coverage failure is reported as that, and no document is added to fix it. Every result
then gives three figures, computed separately:

1. **Coverage ceiling:** the share of cases whose essential provisions are all in the
   corpus, which even a perfect retriever cannot exceed.
2. **Retrieval given coverage:** the `essential_in_corpus_*` metrics.
3. **End to end:** the raw `essential_*` metrics.

## Order of work

1. List `C3` candidates from the corpus text, and `C2` and `C4` from the portal, as
   metadata only. Check gold coverage only after the lists are fixed.
2. State the document count, passage estimate, and collection time before downloading.
3. Collect, process, embed, freeze as `corpus-v2`, then repeat the baseline runs.

## Candidates and gold coverage (04/11/2026)

The portal has no legal status, so "in force" in `C4` is approximated by the latest law of
each name and the laws amending it, minus laws listed as ended
(`scripts/select_corpus_v2.py`). Result: 798 new documents (405 `C2`, 88 `C3`, 305 `C4`),
about 35,000 passages by average size. The lists were fixed before gold coverage was
checked.

Of 30 essential provisions in the 12 scored cases, the rules admit 28, and 10 cases have
all of theirs admitted.

| Document | Rule | Status |
| --- | --- | --- |
| Circular 84/2025/TT-BNNMT (A2) | None: no tax document cites it | Coverage failure |
| Law 64/2025/QH15 (A7) | None as listed | Listing gap: `C4` should admit it, but the 2025 search hit the result cap. Fix the listing for all 2025 laws, not for this law |
| Circular 80/2021/TT-BTC (A4), 25/2018/TT-BTC (A7, L2) | `C3` | Admitted, but in neither source: official Gazette files found 05/11/2026, see "Official files for the two circulars" |

Without those files the ceiling is 8 of 12 cases (A2, A4, A7, L2 fall short). With them it
is 10, and fixing the 2025 listing makes it 11; A2 stays a coverage failure. Known listing limits: six searches stayed at the
cap, one failed, and 245 of 379 cited numbers were not on the portal; the ministry
database has not been searched for them.

## Collection trial (04/11/2026)

Twenty documents drawn at random from the selection in proportion to each rule (10 `C2`, 2
`C3`, 8 `C4`) were downloaded and processed in the API image, limited to one CPU, with no
network or database (`data/evaluation/corpus/collection-trial-v2.json`). All 20 succeeded,
in about 34 minutes: 66 s per document, or 101 s with one outlier
(`124/2020/QH14`, 778 s for 9 pages, not yet explained).

Projected for all 798 documents: about 15-22 hours of processing and about 57,000 passages,
not the 35,000 estimated above, because laws averaged 105 passages in the sample. Laptop
timings may differ from the Azure vCPU, and the `C3` figure rests on two documents.

## Listing update (04/11/2026)

This replaces the counts above. The 2025 law search and the capped tax searches were
narrowed with keywords from listed titles and a fixed list of tax topics, adding 6 laws
and 42 tax documents, including Law 64/2025. The first citation lookup searched for `ND-CP`
instead of `NĐ-CP`, which wrongly recorded most decrees as missing; repeating it raised
`C3` from 134 to 299 of 379 cited numbers.

The selection is now 935 new documents (420 `C2`, 211 `C3`, 304 `C4`). By the trial's
per-rule averages that is about 64,000 passages and 19 hours of processing, on a corpus of
61,208 passages today. The `C3` averages rest on two documents.

`C4` now admits Law 64/2025, so 29 of 30 essential provisions are admitted. Without
official files for Circulars 80/2021 and 25/2018 the ceiling stays at 8 of 12 cases, and
with them it is 11. Circular 84/2025 (A2) remains a coverage failure.

Still open in the listing: one search at the cap (`2016/8/mức thu`), and 80 cited numbers
found on neither the portal nor the cached ministry listings, including those two
circulars. A full ministry listing across every field was stopped after 39 minutes
without a result: it pages through the whole database with no number filter.

The slow trial document (`124/2020/QH14`) took about 32 seconds when repeated, so its 778 s
was not caused by the file.

## Ministry search result (04/11/2026)

Paging through the ministry's circulars, joint circulars, and decrees (7,295 records, about
45 minutes) raised `C3` from 299 to 339 of 379 cited numbers. The selection is now 975 new
documents (420 `C2`, 251 `C3`, 304 `C4`), about 66,000 passages and 20 hours by the trial's
averages. 40 numbers stay unresolved; Circulars 80/2021 and 25/2018 were among them until
they were found in the Gazette (below).

Each record's status and expiry date is kept in `data/evaluation/corpus/mof-status.json`.

The ministry's status also tests the repeal list (`data/evaluation/repeals/corpus-v1.json`),
though not as ground truth, since it lists `94/2010/TT-BTC` as in force although Circular
99/2016 says it ended. 1,111 of the 2,026 corpus documents are in these records. Where the
ministry and the list both say a document ended (64 documents), the date matches for 57,
is within a year for 5, and differs further for 2. The ministry lists 178 documents from
the repeal list as in force, not yet examined. It lists 184 corpus documents as expired,
of which the repeal list has only 64, so 120 could be removed that the filter keeps.

## Official files for the two circulars (05/11/2026)

Both are in the Official Gazette (Công báo), `congbao.chinhphu.vn`, a source we do not
collect from. They are saved in `data/local/supplement/` (not committed), with the page
addresses in `data/corpus/gold_supplement.json`. Both are now in the database, as part of
`corpus-v1.2`. Neither is in `selected-v2.json`, so a `corpus-v2` built on a new database
must load them from the supplement.

| Circular | Gazette issues | Pages | SHA-256 |
| --- | --- | --- | --- |
| 80/2021/TT-BTC | 959 to 974, eight parts merged in order | 760 | `81508854a4c42be68bd09c8cd13b37f114b7081172bce9182a47e7568ccf1e3e` |
| 25/2018/TT-BTC | 499 + 500 | 7 | `e42cbdf9dbff1904346583e81097e954dffc3837b009df0c64eddd61aa36ffa4` |

Checked: all 89 articles of 80/2021 and all 5 of 25/2018 are found, each ends in its
signature block, and the gold provisions are present (80/2021 Art 21 and Art 40(3),
25/2018 Art 2). Both are the text as first published; later amendments of 80/2021 are
separate documents. See the next section for how their text is read.

## Split syllables in PDF text (05/11/2026)

`pypdf` cuts syllables on some PDF fonts (`thực` read as `th ực`). `extract_pages` now
counts these and, above 5 per 1,000 words, uses `pypdfium2`'s text when that is cleaner.
Both Gazette circulars fall from about 80 per 1,000 words in the operative text to almost
none: 25/2018 gives 14 passages, and 80/2021 gives 963 (592 of them appendix forms under
Art 89). 80/2021 has 964 passages as loaded, after OCR of its 9 pages without usable text.

A read-only count over `corpus-v1` finds 8 PDFs above 10 per 1,000 words, 658 of 61,208
passages:

| Document | Per 1,000 words | Passages |
| --- | --- | --- |
| 20/2008/QĐ-BTC | 67.2 | 9 |
| 32/2018/QH14 | 64.9 | 181 |
| 31/2018/QH14 | 56.0 | 156 |
| 191/2010/TT-BTC | 41.1 | 23 |
| 48/2024/QH15 | 11.5 | 86 |
| 56/2024/QH15 | 11.4 | 63 |
| 254/2013/TT-BTC | 11.0 | 5 |
| 84/2025/TT-BNNMT | 10.7 | 135 |

Few documents, but essential provisions of 8 of 12 gold cases are in them (A1, A2, A4, A5,
A6, A8, L3, L4), mostly VAT Law 48/2024. Reprocessing them as `corpus-v1.1` changed almost
no rank, so split syllables were not why those provisions were missed: see
[retrieval-experiments.md](retrieval-experiments.md). `191/2010/TT-BTC` stays broken, at 31.9
per 1,000 words.

## To do

The database holds `corpus-v1.2`; `corpus-v2` is not started. Results so far show that more
documents do not by themselves make provisions retrievable. The keyword term limit is now gone, so
this decision is open ([open work](evaluation-status.md#open-work)).

1. Back up the database, start Airflow, collect and process the selection (`C2` and `C3`
   first, or all 975), and freeze `corpus-v2`.
2. Repeat the baselines on `corpus-v2`, reporting coverage ceiling, retrieval given
   coverage, and end to end.
