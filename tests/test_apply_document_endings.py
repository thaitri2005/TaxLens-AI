import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/apply_document_endings.py"


def _module():
    spec = importlib.util.spec_from_file_location("apply_document_endings", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_related_documents_get_the_corpus_spelling_or_the_official_one() -> None:
    script = _module()
    folded = {"48/2024/qh15": "48/2024/QH15"}
    unresolved: set[str] = set()

    assert script._document_number("ministry status", folded, unresolved) is None
    assert script._document_number("48/2024/qh15", folded, unresolved) == "48/2024/QH15"
    assert script._document_number("106/2007/qd-btc", folded, unresolved) == "106/2007/QĐ-BTC"
    assert script._document_number("12/2011/qd-ttg", folded, unresolved) == "12/2011/QĐ-TTg"
    assert script._document_number("25/2013/nd-cp", folded, unresolved) == "25/2013/NĐ-CP"
    assert script._document_number("97/2006/TT-BTC", folded, unresolved) == "97/2006/TT-BTC"
    assert unresolved == {"106/2007/qd-btc", "12/2011/qd-ttg", "25/2013/nd-cp", "97/2006/TT-BTC"}
