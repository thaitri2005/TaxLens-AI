"""Find explicit legal references in passage text.

Vietnamese provisions cite each other as ``điểm l khoản 1 Điều 2 Luật Thuế tiêu thụ đặc
biệt`` or ``Điều 5 Nghị định số 181/2025/NĐ-CP``. Matching runs on unaccented lowercase
text, because OCR often loses diacritics. A reference with no target, or one ending in
``này``, points at the document that contains it.
"""

import re
from dataclasses import dataclass

from taxlens.retrieval.text import fold_vietnamese

_NUMBER = r"\d{1,4}/(?:\d{4}/)?[a-z0-9]+(?:-[a-z0-9]+)*"
_TYPE = r"luat|nghi dinh|thong tu|nghi quyet|quyet dinh"
_PINPOINT = re.compile(
    r"(?:diem\s+(?P<point>[a-z])\s*,?\s+)?"
    r"(?:khoan\s+(?P<clause>\d+[a-z]?)\s*,?\s+)?"
    r"dieu\s+(?P<article>\d+[a-z]?)\b"
    r"(?P<target>(?:\s*,?\s*(?:cua|tai)?\s*(?:" + _TYPE + r")\b[^.;]{0,90})?)"
)
_DOCUMENT = re.compile(r"\b(?P<type>" + _TYPE + r")\s+(?:so\s+)?(?P<number>" + _NUMBER + r")")
_BARE_NUMBER = re.compile(r"\b(?P<number>\d{1,4}/\d{4}/[a-z0-9]+(?:-[a-z0-9]+)*)")
_LAW_NAME = re.compile(r"\bluat\s+(?P<name>[a-z\s]{3,70})")
# Words that end a law's name in running text.
_NAME_STOP = re.compile(
    r"\s(?:so|nam|ngay|va|hoac|thi|la|quy dinh|duoc|da|sua doi|hien hanh|nay|ve viec)\b.*$"
)
_ENACTING_LINE = re.compile(r"^\W*can cu\b", re.MULTILINE)


@dataclass(frozen=True)
class LegalReference:
    article: str | None
    clause: str | None = None
    point: str | None = None
    document_number: str | None = None
    """Folded number as written; None when the target is not given by number."""
    law_name: str | None = None
    """Folded law name, when the target is a law named without its number."""
    same_document: bool = False


def find_references(text: str) -> list[LegalReference]:
    """References in the order they appear, leaving out "Căn cứ" enacting clauses."""

    lines = [
        line
        for line in fold_vietnamese(text).lower().splitlines()
        if not _ENACTING_LINE.match(line)
    ]
    folded = "\n".join(lines)
    references: list[LegalReference] = []
    pinned_numbers: set[str] = set()
    for match in _PINPOINT.finditer(folded):
        target = match["target"] or ""
        if _is_article_heading(folded, match, target):
            continue
        number = _DOCUMENT.search(target) or _BARE_NUMBER.search(target)
        name = None if number else _law_name(target)
        if number:
            pinned_numbers.add(number["number"])
        references.append(
            LegalReference(
                article=match["article"],
                clause=match["clause"],
                point=match["point"],
                document_number=number["number"] if number else None,
                law_name=name,
                same_document=not number and not name,
            )
        )
    for match in _DOCUMENT.finditer(folded):
        if match["number"] not in pinned_numbers:
            pinned_numbers.add(match["number"])
            references.append(LegalReference(article=None, document_number=match["number"]))
    return references


def _is_article_heading(text: str, match: re.Match[str], target: str) -> bool:
    """``Điều 15. Hoàn thuế`` at the start of a line names the article; it refers to nothing."""

    at_line_start = match.start() == 0 or text[match.start() - 1] == "\n"
    return at_line_start and not target and text[match.end() : match.end() + 1] in (".", ":")


def _law_name(target: str) -> str | None:
    match = _LAW_NAME.search(target)
    if not match:
        return None
    name = _NAME_STOP.sub("", " " + " ".join(match["name"].split())).strip()
    return name or None
