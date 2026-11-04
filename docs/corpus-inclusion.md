# Corpus inclusion rules for corpus-v2

Written before any candidate list was made, and without reading the gold set for
documents to add. `corpus-v1` closed its gaps with `collect_sources.py --cited-by`, which
collects what the gold set cites: those documents enter because they are the answers, and
a non-tax law then has no similar documents around it. These rules replace that step.

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
| Circular 80/2021/TT-BTC (A4), 25/2018/TT-BTC (A7, L2) | `C3` | Admitted, but in neither source: needs an official file, otherwise a coverage failure |

Without those files the ceiling is 8 of 12 cases (A2, A4, A7, L2 fall short). With them it
is 10, and fixing the 2025 listing makes it 11; A2 stays a coverage failure. Known listing limits: six searches stayed at the
cap, one failed, and 245 of 379 cited numbers were not on the portal; the ministry
database has not been searched for them.
