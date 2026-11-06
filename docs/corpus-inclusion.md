# Corpus inclusion rules

Written before any candidate list, and without reading the gold set for documents to add, so documents
do not enter because they are the answers. `corpus-v2` is built under these rules: results are in
[evaluation-status.md](evaluation-status.md).

## Rules

A document enters if it is national and normative (a law, National Assembly resolution, decree, or
circular, not a provincial document or official letter) and meets one rule. It records the first met.

| Rule | Admits | Why |
| --- | --- | --- |
| `C1 tax` | What `corpus-v1` collected by subject: the portal's tax category, the ministry's tax selection | The existing corpus |
| `C2 tax title` | Any portal category, if `is_tax_title` accepts the title | The portal does not file every tax document under tax |
| `C3 cited` | Cited by number in the operative text of at least 2 tax documents still in force | A rule tax documents apply is part of tax law |
| `C4 any law` | Every National Assembly law in force, on any subject | Tax rules use categories other laws define, and unrelated laws keep non-tax laws from being trivially easy to find |

Enacting clauses (`Căn cứ ...`) do not count as citations. "In force" uses
`data/evaluation/repeals/corpus-v1.json`. The threshold of 2 is not tuned. The portal has no legal
status, so `C4` takes the latest law of each name and the laws amending it, minus those listed as ended.

## What is reported

For each gold essential provision: in corpus (with its rule), or a coverage failure, for which no
document is added. Results give three figures: **coverage ceiling** (cases with all essential
provisions in the corpus), **retrieval given coverage** (`essential_in_corpus_*`), and **end to end**
(`essential_*`).

## The selection

`selected-v2.json` holds 975 new documents: 420 `C2`, 251 `C3`, 304 `C4`, 935 from the portal and 40
from the ministry. 973 are in, added by `collect_selected`. The rules admit 29 of 30 essential
provisions. Circular 84/2025/TT-BNNMT (A2) is a coverage failure, though it is held from the earlier
collection.

Circulars 80/2021 and 25/2018 are in neither source. Their Official Gazette files are in
`data/local/supplement/` (not committed), with addresses in `data/corpus/gold_supplement.json`. A
build on a new database must load them from there.

Passages were underestimated: 46,932 estimated against 77,904, because the estimate assumed 49 per law
from the few held, and the 344 new laws average 112.

Listing limits: one portal search stayed at the result cap (`2016/8/mức thu`), and 40 cited numbers
were found in neither source. Ministry status and expiry dates are in
`data/evaluation/corpus/mof-status.json`. They are not ground truth: `94/2010/TT-BTC` is listed in force
though Circular 99/2016 ended it. Where both give an end date (64 documents), 57 match.
