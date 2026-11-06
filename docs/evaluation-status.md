# Status

Where TaxLens stands as of 06/11/2026. Rewritten as things change. What has been tried is in
[retrieval-experiments.md](retrieval-experiments.md): read it before running anything.

## What is live

- **Site:** `a9c4ac7`, answering with `google/gemma-3-27b-it`. **The faster model
  `openai/gpt-oss-120b` is in the code and needs a release.**
- **Corpus:** `corpus-v2`, frozen: 2,991 documents, 3,000 versions, 144,600 passages, all embedded.
- **Airflow:** stopped. Keep it stopped, and the daily DAG paused, or the frozen corpus changes.
- **Speed:** a whole answer takes 4-9 s on the new model, from a laptop, against 49-97 s. The first
  question after about 5 idle minutes also waits for the API to start, about 1 minute or more.

## Results

Essential recall on `corpus-v2`, 12 gold cases, full coverage in brackets where not 0. Too few cases
to separate most methods.

| Method | K = 5 | K = 10 | K = 20 |
| --- | --- | --- | --- |
| Keyword | 0.22 (0.08) | 0.30 (0.25) | 0.42 (0.25) |
| Hybrid (what the site does) | 0.10 | 0.30 (0.08) | 0.41 (0.25) |
| **Hybrid + filter for ended documents** | **0.35 (0.17)** | **0.45 (0.25)** | **0.45 (0.25)** |
| Issue-guided | 0.04 | 0.10 | 0.15 |

On `corpus-v1.2`, with TCVN3 unconverted: hybrid 0.30, 0.41, 0.45; with filter 0.38, 0.45, 0.45.

**What these mean.** Adding documents lowered recall because old, ended documents crowd the top: new
documents took 25-28% of the top 10. The filter restores it, but rests on 12 cases, was built after
seeing the problem, and includes rules no legal expert has validated. The TCVN3 repair and appendix
labels changed in the same step, and their effect was not separated.

## Corpora

Manifests are in `data/evaluation/corpus/`. Runs against an older corpus stop at the corpus check.

| Corpus | What it is | Documents | Passages | Fingerprint |
| --- | --- | --- | --- | --- |
| `corpus-v1` | Original | 2,026 | 61,208 | `317f5a0d` |
| `corpus-v1.1` | 8 PDFs repaired | 2,026 | 61,204 | `cd396fa3` |
| `corpus-v1.2` | Circulars 80/2021 and 25/2018 added | 2,028 | 62,182 | `7df84879` |
| **`corpus-v2`** | [Rules](corpus-inclusion.md), TCVN3 repaired, 41 numbers corrected | 2,991 | 144,600 | `62b499cf` |

## Known problems

1. **The site can cite ended law.** The filter exists only in evaluation. Read by hand, answers cite
   Decree 123/2008, Law 13/2008 and Circular 32/2011. Whether to apply it is undecided.
2. **Most essential provisions are still missed.** About half of the hardest need a legal step the
   question does not state ([diagnosis](retrieval-experiments.md#retrieval)).
3. **Answer model trade-offs:** the faster model costs about $0.002 an answer, against $0.0003, and can
   mislabel a document's type. It depends on Groq and Cerebras staying on the router.
4. **Answer quality is unmeasured:** only lexical checks on 5 questions, with no gold answers.
5. **Duplicates:** 9 document numbers hold near-identical second versions, and 5 numbers with stray
   spaces (`148/2013/TT- BTC`) duplicate clean ones. Both copies can appear in results. Nothing was
   deleted.
6. **Numbers still uncertain:** `93/1998/QĐ/TCKT` and `25/2026/TT-BTC`, where header and portal
   disagree; `124/2026/TT-BTC` was inferred from a misread header and date. The other 50 flags in the
   library are OCR misreads, shortened headers, or citations picked up as headers.
7. **Failed or absent:** 9 documents have no text (7 Excel workbooks filed as `.rtf`, a 2-byte file,
   `204/2004/NĐ-CP`). `56/2009/NĐ-CP` (invalid file on the portal) and `38/2015/TT-BTC` (download failed)
   were not collected. Originals of some amendments, such as `68/2025` and `83/2024/TT-BTC`, are not
   held.
8. **Small text issues:** `191/2010/TT-BTC` keeps split syllables; words like `cã` can stay
   unconverted in mixed-font lines; mislabelled numbers can recur, since collection trusts the listing
   and only flags a mismatch.

## To do

In suggested order:

1. Add gold cases, to at least 50: 12 cannot separate methods, and the best results need independent
   evidence.
2. Have a tax expert review the filter's inferred rules, the 178 documents the ministry says are in
   force but our list ends, and the alternative evidence sets.
3. Decide on ended documents for the site. The cautious option is explicit repeals and ministry
   dates, which needs one 6-minute run on `corpus-v2` first.
4. Tell the professor: all earlier results were measured with the TCVN3 bug, and hybrid fell from 0.41
   to 0.30 before the filter brought it to 0.45.
5. Plan a step that works out which law a question depends on.
6. Build answer evaluation with reviewed labels.
7. Remove duplicates and settle the uncertain numbers.

**Azure clean-up, for the owner:** delete old ACR images ([commands](operations.md#costs))
and remove stale database firewall rules. Leave `CreditScorecardWOEIV` alone: it serves another live project.
