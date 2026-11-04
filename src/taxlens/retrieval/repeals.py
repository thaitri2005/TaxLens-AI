"""Find which documents stopped applying, from what the corpus itself says.

The corpus records no end date: collection keeps "in force" documents and the ministry
still lists old circulars as in force. New documents do say what they end, so this reads
that from their text. Matching runs on unaccented lowercase text because of OCR.

Three rules, weakest last:
- ``explicit``: a document says another one ends (``hết hiệu lực``, ``bãi bỏ``, ``thay
  thế``). A statement about an article, clause, or form of it ends only that part and is
  ignored.
- ``guidance``: a document whose title says it guides or details a document that ended.
- ``amendment``: a document whose title says it amends a document that ended.

``guidance`` and ``amendment`` are inferences, which a legal expert should validate. A
fourth rule, ``ministry``, is added by ``scripts/add_ministry_expiry.py``: the Ministry of
Finance's own status and expiry date. A document with no
such statement is kept, so the filter errs towards keeping.
"""

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from taxlens.retrieval.text import fold_vietnamese

_NUMBER = r"\d{1,4}/\d{4}/[a-z0-9]+(?:-[a-z0-9]+)*|\d{1,4}/[a-z]+(?:-[a-z]+)+"
_NUMBER_PATTERN = re.compile(rf"(?<![\d/])(?:{_NUMBER})")
_TYPE = r"(?:thong tu(?: lien tich| lien bo)?|nghi dinh|luat|phap lenh|nghi quyet|quyet dinh)"
_NAMED = rf"{_TYPE}\s+(?:so\s+)?(?:\d+\s+)?(?P<number>{_NUMBER})"
# The ending verb, then the document it ends.
_ENDS_NEXT = re.compile(
    rf"(?:\bbai bo\s+|{_TYPE} nay thay the\s+(?:cho\s+)?|\bthay the\s+|\bbai bo cac\s+){_NAMED}"
)
# The document, then the ending verb in the same sentence.
_ENDS_PREVIOUS = re.compile(
    rf"\b{_TYPE}[^.;:]{{0,70}}?(?<![\d/])(?P<number>{_NUMBER})[^.;:]{{0,250}}?"
    r"\b(?:het hieu luc|bi bai bo|duoc bai bo|duoc thay the)\b"
)
# "... hết hiệu lực:" or "Nghị định này thay thế:" opens a list of ended documents.
_LIST_OPENER = re.compile(
    rf"(?:het hieu luc(?: thi hanh)?|bai bo|{_TYPE} nay thay the(?: cho)?)"
    rf"(?:\s+(?:cac|nhung) van ban(?: sau(?: day)?)?)?\s*:\s*"
)
_LIST_ITEM = re.compile(rf"^\W*(?:[a-z0-9][.)]\s*)?\W*{_NAMED}")
# Words before a document number that mean only a part of it is meant.
_PART_OF = re.compile(
    r"\b(?:dieu|khoan|diem|muc|chuong|phu luc|mau(?: so)?|bieu mau|vi du|noi dung|quy dinh)\b"
    r"[^.;:]*$"
)
_STILL_APPLIES = re.compile(r"tiep tuc|chua het hieu luc|khong het hieu luc|cho den khi")
_EFFECTIVE_FROM = re.compile(
    r"(?:co hieu luc|hieu luc thi hanh)[^.;]{0,40}?(?:tu|ke tu)\s+ngay\s+"
    r"(?P<day>\d{1,2})\s*(?:/|-|thang)\s*(?P<month>\d{1,2})\s*(?:/|-|nam)\s*(?P<year>\d{4})"
)
_GUIDES = re.compile(r"\b(?:huong dan|quy dinh chi tiet)\b")
_AMENDS = re.compile(r"\bsua doi\b")


RULES = ("explicit", "guidance", "amendment", "ministry")


@dataclass(frozen=True)
class Repeal:
    document_number: str
    ended_on: date
    rule: str
    by: str


def ended_documents(
    stored: Mapping[str, Mapping[str, str]], on: date, rules: Collection[str] = RULES
) -> tuple[str, ...]:
    """Numbers of the documents a stored repeal list says had ended by this date."""

    return tuple(
        sorted(
            number
            for number, repeal in stored.items()
            if repeal["rule"] in rules and date.fromisoformat(repeal["ended_on"]) <= on
        )
    )


def normalize(text: str) -> str:
    return " ".join(fold_vietnamese(text).lower().split())


def explicit_targets(text: str) -> set[str]:
    """Numbers, folded, of the documents this passage says end entirely."""

    folded = normalize(text)
    targets: set[str] = set()
    for sentence in re.split(r"(?<=[.;])\s", folded):
        if _STILL_APPLIES.search(sentence):
            continue
        for pattern in (_ENDS_NEXT, _ENDS_PREVIOUS):
            for match in pattern.finditer(sentence):
                if not _PART_OF.search(sentence[: match.start("number")]):
                    targets.add(match["number"])
    opener = _LIST_OPENER.search(folded)
    if opener:
        for item in re.split(r";\s*|\.\s+", folded[opener.end() :]):
            item_match = _LIST_ITEM.match(item)
            if item_match:
                targets.add(item_match["number"])
    return targets


def effective_date_in(text: str) -> date | None:
    match = _EFFECTIVE_FROM.search(normalize(text))
    if not match:
        return None
    try:
        return date(int(match["year"]), int(match["month"]), int(match["day"]))
    except ValueError:
        return None


def infer_repeals(
    explicit: Iterable[tuple[str, str, date]],
    titles: dict[str, str],
) -> dict[str, Repeal]:
    """Apply the rules until nothing changes; the earliest end of a document wins.

    ``explicit`` holds ``(ended number, ended by, date)``; ``titles`` maps each document's
    number to its title. Numbers are returned as the corpus writes them.
    """

    numbers = {normalize(number): number for number in titles}
    repeals: dict[str, Repeal] = {}
    for target, by, ended_on in explicit:
        # A parent outside the corpus still ends the guidance inside it.
        number = numbers.get(target, target)
        if number != by:
            _keep_earliest(repeals, Repeal(number, ended_on, "explicit", by))
    cited = {number: _cited_numbers(title, number) for number, title in titles.items()}
    laws = _law_names(titles)
    changed = True
    while changed:
        changed = False
        for number, title in titles.items():
            if number in repeals:
                continue
            folded = normalize(title)
            rule = "amendment" if _AMENDS.search(folded) else None
            rule = "guidance" if _GUIDES.search(folded) else rule
            if rule is None:
                continue
            parents = [numbers.get(parent, parent) for parent in cited[number]]
            if rule == "guidance":
                parents += _named_parents(folded, _issued_year(number), laws)
            for parent in parents:
                ended = repeals.get(parent)
                # A title that names the document it replaces does not end with it.
                if ended and ended.by != number and _issued_year(number) <= ended.ended_on.year:
                    repeals[number] = Repeal(number, ended.ended_on, rule, parent)
                    changed = True
                    break
    return repeals


def _law_names(titles: dict[str, str]) -> dict[str, list[tuple[int, str]]]:
    """Folded law name -> ``(year, number)`` of each law of that name, amending laws left out."""

    laws: dict[str, list[tuple[int, str]]] = {}
    for number, title in titles.items():
        folded = normalize(title)
        if "/QH" in number and folded.startswith("luat ") and not _AMENDS.search(folded):
            laws.setdefault(folded, []).append((_issued_year(number), number))
    return laws


def _named_parents(title: str, year: int, laws: dict[str, list[tuple[int, str]]]) -> list[str]:
    """For each law the title names, the law of that name in force when it was issued."""

    parents = []
    for name, versions in laws.items():
        if re.search(rf"\b{re.escape(name)}\b", title):
            earlier = [version for version in versions if version[0] <= year]
            if earlier:
                parents.append(max(earlier)[1])
    return parents


def _cited_numbers(title: str, own_number: str) -> list[str]:
    own = normalize(own_number)
    return [found for found in _NUMBER_PATTERN.findall(normalize(title)) if found != own]


def _issued_year(number: str) -> int:
    match = re.search(r"/((?:19|20)\d\d)/", number)
    return int(match[1]) if match else 0


def _keep_earliest(repeals: dict[str, Repeal], repeal: Repeal) -> None:
    current = repeals.get(repeal.document_number)
    if current is None or repeal.ended_on < current.ended_on:
        repeals[repeal.document_number] = repeal
