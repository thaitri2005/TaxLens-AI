"""Find which documents stopped applying, from what the corpus itself says.

The corpus records no end date: collection keeps "in force" documents and the ministry
still lists old circulars as in force. New documents do say what they end, so this reads
that from their text. Matching runs on unaccented lowercase text because of OCR.

Three rules, weakest last:
- ``explicit``: a document says another one ends (``hết hiệu lực``, ``bãi bỏ``, ``thay
  thế``), or that it continues in force until a date (``tiếp tục có hiệu lực đến ngày``,
  ending the next day). A statement about an article, clause, or form of it ends only that
  part and is ignored. A list of ended documents split across passages is followed into
  the passages of the same clause (``list_continuation_targets``).
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
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum

from taxlens.retrieval.text import fold_vietnamese

_NUMBER = r"\d{1,4}/\d{4}/[a-z0-9]+(?:-[a-z0-9]+)*|\d{1,4}/[a-z]+(?:-[a-z]+)+"
_NUMBER_PATTERN = re.compile(rf"(?<![\d/])(?:{_NUMBER})")
_TYPE = r"(?:thong tu(?: lien tich| lien bo)?|nghi dinh|luat|phap lenh|nghi quyet|quyet dinh)"
_NAMED = rf"{_TYPE}\s+(?:so\s+)?(?:\d+\s+)?(?P<number>{_NUMBER})"
# The ending verb, then the document it ends.
_ENDS_NEXT = re.compile(
    rf"(?:\bbai bo\s+(?:cac\s+)?|{_TYPE} nay thay the\s+(?:cho\s+)?(?:cac\s+)?"
    rf"|\bthay the\s+(?:cho\s+)?(?:cac\s+)?){_NAMED}"
)
# What may stand between two documents of one run ("Thông tư số X ngày 15 tháng 12 năm 2005
# của Bộ Tài chính, Thông tư số Y"): a date, an issuer, then a comma or "và". Anything else,
# such as a title ("hướng dẫn Nghị định số Z"), ends the run.
_RUN_GAP = re.compile(
    r"\s*(?:ngay\s+\d{1,2}\s*(?:/|-|thang)\s*\d{1,2}\s*(?:/|-|nam)\s*\d{4}\s*)?"
    r"(?:cua\s+(?:bo truong\s+)?(?:bo tai chinh|chinh phu|thu tuong chinh phu|quoc hoi"
    r"|uy ban thuong vu quoc hoi|tong cuc thue|tong cuc hai quan)\s*)?"
    r"(?:,\s*(?:va\s+)?|va\s+)(?:cac\s+)?"
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
# An item may start with a page number left by OCR ("16 j) Thông tư số ...").
_LIST_ITEM = re.compile(rf"^\W*(?:\d{{1,3}}\W+)?(?:[a-z0-9][.)]\s*)?\W*{_NAMED}")
# A numbered clause ("4. Thông tư này ...") ends a list.
_NEXT_CLAUSE = re.compile(r"(?:^|\s)\d{1,2}\.\s+[a-z]")
# "... tiếp tục có hiệu lực thi hành đến (hết) ngày 30 tháng 6 năm 2022": ends the next day.
_CONTINUES_UNTIL = re.compile(
    r"tiep tuc (?:co )?hieu luc(?: thi hanh)? (?:den|cho den) (?:het )?ngay\s+"
    r"(?P<day>\d{1,2})\s*(?:/|-|thang)\s*(?P<month>\d{1,2})\s*(?:/|-|nam)\s*(?P<year>\d{4})"
)
_NAMED_PATTERN = re.compile(_NAMED)
# Words just before a named document that mean only part of it is meant ("Điều 5 của").
_PART_BEFORE = re.compile(
    r"(?:\b(?:dieu|khoan|diem|muc|chuong|phu luc)\b[^,;]*|"
    r"\b(?:dieu|khoan|diem)\b[^;]{0,30}\bcua\s*)$"
)
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
# Endings the site acts on: a document's own statement, or the ministry's record.
CONFIRMED_RULES = ("explicit", "ministry")
# Endings the site only flags, until a legal expert validates the rules.
INFERRED_RULES = ("guidance", "amendment")


@dataclass(frozen=True)
class Repeal:
    document_number: str
    ended_on: date
    rule: str
    by: str


class EndState(StrEnum):
    ENDED = "ENDED"
    """A confirmed rule ended it on or before the date."""
    MAY_HAVE_ENDED = "MAY_HAVE_ENDED"
    """Only an inferred rule says it ended on or before the date."""
    ENDS_LATER = "ENDS_LATER"
    """It is recorded to end after the date."""


def ending_note(
    document_number: str,
    ended_on: date | None,
    basis: str | None,
    ended_by: str | None,
    on: date,
) -> str | None:
    """One sentence on a document's recorded ending as of ``on``, for answers and prompts."""

    state = end_state(ended_on, basis, on)
    if state is None or ended_on is None:
        return None
    when = ended_on.strftime("%d/%m/%Y")
    if state is EndState.ENDS_LATER:
        return f"{document_number} is recorded to stop applying on {when}."
    if state is EndState.ENDED:
        source = (
            f"ended by {ended_by}"
            if basis == "explicit" and ended_by
            else "according to the Ministry of Finance's record"
        )
        return (
            f"{document_number} stopped applying on {when} ({source}); its text states the law "
            "before that date only."
        )
    relation = "guides" if basis == "guidance" else "amends"
    return (
        f"{document_number} may have stopped applying on {when}: it {relation} "
        f"{ended_by or 'a document'}, which ended then. Confirm it still applies."
    )


_VIETNAM = timezone(timedelta(hours=7))


def today_in_vietnam() -> date:
    """Today's date where the law applies (UTC+7, no daylight saving)."""

    return datetime.now(UTC).astimezone(_VIETNAM).date()


def end_state(ended_on: date | None, basis: str | None, on: date) -> EndState | None:
    """Whether a document with this recorded ending had ended by ``on``; None if never."""

    if ended_on is None or basis is None:
        return None
    if ended_on > on:
        return EndState.ENDS_LATER
    return EndState.ENDED if basis in CONFIRMED_RULES else EndState.MAY_HAVE_ENDED


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
        for match in _ENDS_NEXT.finditer(sentence):
            if not _PART_OF.search(sentence[: match.start("number")]):
                targets.add(match["number"])
                targets |= _run_after(sentence, match.end())
        for match in _ENDS_PREVIOUS.finditer(sentence):
            if not _PART_OF.search(sentence[: match.start("number")]):
                targets.add(match["number"])
    opener = _LIST_OPENER.search(folded)
    if opener:
        targets |= _list_items(folded[opener.end() :])
    return targets


def opens_list(text: str) -> bool:
    """Whether this passage opens a list of ended documents."""

    return _LIST_OPENER.search(normalize(text)) is not None


def list_continuation_targets(text: str) -> set[str]:
    """Numbers, folded, of list items at the start of a passage that continues a list.

    Only meaningful for a passage of the same article and clause as one that opens a list
    (``opens_list``), since passages are split by size.
    """

    folded = normalize(text)
    if _LIST_OPENER.search(folded):
        return set()
    return _list_items(folded)


def _list_items(folded_list: str) -> set[str]:
    end = _NEXT_CLAUSE.search(folded_list)
    targets: set[str] = set()
    for item in re.split(r";\s*|\.\s+", folded_list[: end.start() if end else None]):
        item_match = _LIST_ITEM.match(item)
        if item_match:
            targets.add(item_match["number"])
            targets |= _run_after(item, item_match.end())
    return targets


def _run_after(text: str, position: int) -> set[str]:
    """Numbers of the documents that continue a run from ``position`` ("X, Y và Z")."""

    numbers: set[str] = set()
    while True:
        gap = _RUN_GAP.match(text, position)
        if not gap:
            return numbers
        named = _NAMED_PATTERN.match(text, gap.end())
        if not named:
            return numbers
        numbers.add(named["number"])
        position = named.end()


def sunset_targets(text: str) -> dict[str, date]:
    """Folded numbers of documents said to continue in force until a date, with the day after."""

    found: dict[str, date] = {}
    for sentence in re.split(r"(?<=[.;])\s", normalize(text)):
        until = _CONTINUES_UNTIL.search(sentence)
        if not until:
            continue
        try:
            last_day = date(int(until["year"]), int(until["month"]), int(until["day"]))
        except ValueError:
            continue
        for named in _NAMED_PATTERN.finditer(sentence[: until.start()]):
            if not _PART_BEFORE.search(sentence[max(0, named.start() - 60) : named.start()]):
                found[named["number"]] = last_day + timedelta(days=1)
    return found


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
