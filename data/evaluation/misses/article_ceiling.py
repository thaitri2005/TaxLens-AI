"""Essential recall when a passage of a provision's article counts (article expansion ceiling)."""
import importlib.util, json
from datetime import date
from pathlib import Path
from taxlens.db import SessionLocal
from taxlens.evaluation.metrics import provision_ranks
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.repeals import ended_documents
from taxlens.retrieval.search import SearchFilters, hybrid_search_chunks
spec = importlib.util.spec_from_file_location("ev", "scripts/evaluate_tax_retrieval.py"); ev = importlib.util.module_from_spec(spec); spec.loader.exec_module(ev)
repeals = json.loads(Path("data/evaluation/repeals/corpus-v2.1-ministry.json").read_text(encoding="utf-8"))["repeals"]
cases = [c for c in ev._gold_set_cases(Path("data/evaluation/gold_set_v1.csv"), True) if c["essential_provisions"]]
provider = get_embedding_provider(); pc = {}; rows = []
with SessionLocal() as s:
    for case in cases:
        day = date.fromisoformat(case["search_date"])
        f = SearchFilters(as_of=day, excluded_document_numbers=ended_documents(repeals, day, ("explicit", "ministry")))
        res = hybrid_search_chunks(s, case["query"], provider, f, 20)
        loc = ev._passage_locators(s, res, pc)
        clause = provision_ranks(loc, case["essential_provisions"])
        art_provs = [[[d, a, None] for d, a, _ in places] for places in case["essential_provisions"]]
        article = provision_ranks(loc, art_provs)
        # passages of distinct articles among the top 5 (how many articles an expansion would add)
        arts5 = len({(l[0], l[1]) for l in loc[:5]})
        rows.append({"case": case["case_id"], "clause": clause, "article": article, "articles_in_top5": arts5})
        print(case["case_id"], clause, article, flush=True)
def recall(key, k):
    v = [sum(r is not None and r <= k for r in row[key]) / len(row[key]) for row in rows]; return round(sum(v) / len(v), 3)
summary = {k: {"clause": recall("clause", k), "article": recall("article", k)} for k in (5, 10, 20)}
print(json.dumps(summary)); Path(__import__("sys").argv[1]).write_text(json.dumps({"summary": summary, "cases": rows}, indent=1), encoding="utf-8")
