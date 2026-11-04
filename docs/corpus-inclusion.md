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
