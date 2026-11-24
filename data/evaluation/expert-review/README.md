# Expert review packet

For the domain expert introduced by Prof. Thanh (24/11/2026). The review page is published as a private
claude.ai artifact (`index.html` with `packet.json`); answers are stored in its database, collection
`reviews`, one document per item, and read back with the ArtifactData tool.

- `collect.py` gathers the content from the corpus and saved runs (no model calls), into `packet-data.json`.
- `packet.json` is the filtered set the page shows: 25 documents flagged as "may have ended", 13 old
  documents with no recorded ending that outrank current law, the essential provisions of the 17 hard
  cases (with L4 and A7's open points), and the 16 graded answers (the judge's grade is shown only after
  the expert gives hers).
- Left out on purpose: the 178 documents the ministry lists as in force but our list ends, approving new
  gold cases, and document numbers that need the originals (see evaluation-status.md, "For people").
