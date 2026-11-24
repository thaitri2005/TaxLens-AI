"""Why 10 provisions stay out of the top 20 even when their issue is named (counted oracle run)."""

import importlib.util
import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.evaluation.metrics import provision_ranks
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.repeals import ended_documents
from taxlens.retrieval.search import (
    SearchFilters,
    hybrid_search_chunks,
    keyword_search_chunks,
    semantic_search_chunks,
)

spec = importlib.util.spec_from_file_location("ev", "scripts/evaluate_tax_retrieval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
MISSES = ["A1#0", "A2#0", "A2#1", "A3#1", "A4#2", "A7#1", "A7#2", "A14#0", "A15#1", "A16#0"]
DEPTH = 500
oracle = json.loads(
    Path("data/evaluation/oracle/oracle-queries-reviewed.json").read_text(encoding="utf-8")
)
repeals = json.loads(
    Path("data/evaluation/repeals/corpus-v2.1-ministry.json").read_text(encoding="utf-8")
)["repeals"]
cases = {c["case_id"]: c for c in ev._gold_set_cases(Path("data/evaluation/gold_set_v1.csv"), True)}
provider = get_embedding_provider()
part_counts = {}
with SessionLocal() as s:
    for miss in MISSES:
        cid, idx = miss.split("#")
        idx = int(idx)
        case = cases[cid]
        prov = case["essential_provisions"][idx]
        day = date.fromisoformat(case["search_date"])
        f = SearchFilters(
            as_of=day,
            excluded_document_numbers=ended_documents(repeals, day, ("explicit", "ministry")),
        )
        doc, art, clause = prov[0]
        print(f"\n===== {miss} {prov}  case date {day}")
        # Is the target there, and does it pass the filters?
        only = replace(f, document_number=doc)
        vec_only = semantic_search_chunks(
            s, provider.embed_query("x").vectors[0], provider, only, 5
        )
        print(f"  passes filters: {bool(vec_only)}; ended entry: {repeals.get(doc)}")
        rows = s.execute(
            select(DocumentChunk.clause_number, DocumentChunk.heading, DocumentChunk.content)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(LegalDocument, LegalDocument.id == DocumentVersion.document_id)
            .where(LegalDocument.document_number == doc, DocumentChunk.article_number == str(art))
        ).all()
        print(f"  passages of article {art}: {len(rows)}; clauses {[r[0] for r in rows]}")
        for c_no, _head, content in rows:
            if clause is None or c_no == str(clause) or c_no is None:
                print(f"    [{c_no}] {len(content)} chars :: {content[:260].replace(chr(10), ' ')}")
        queries = [("QUESTION", case["query"])] + [
            (q["targets"], q["query"]) for q in oracle["cases"].get(cid, {}).get("issues", [])
        ]
        for label, q in queries:
            kw = keyword_search_chunks(s, q, f, DEPTH)
            ve = semantic_search_chunks(s, provider.embed_query(q).vectors[0], provider, f, DEPTH)
            rk = provision_ranks(ev._passage_locators(s, kw, part_counts), [prov])[0]
            rv = provision_ranks(ev._passage_locators(s, ve, part_counts), [prov])[0]
            print(f"  keyword {rk}  vector {rv}  <- [{label}] {q}")
        top = hybrid_search_chunks(
            s, queries[-1][1] if len(queries) > 1 else case["query"], provider, f, 5
        )
        for r in top:
            place = f"art {r.chunk.article_number}({r.chunk.clause_number})"
            title = (r.document.title or "")[:60]
            print(f"     top: {r.document.document_number:20} {place} :: {title}")
        sys.stdout.flush()
