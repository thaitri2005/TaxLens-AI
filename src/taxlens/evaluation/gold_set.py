"""The annotated gold set (data/evaluation/gold_set_v1.csv, docs/annotation-guideline.md).

Annotators write provisions for people to read, e.g.
``E: VAT Law 48/2024 Art 5(1), as amended by Law 149/2025 | S: Decree 181 Art 19(3)``.
This module turns them into the document, article, and clause labels the retrieval
evaluation scores against.
"""

import csv
import re
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

_KINDS = (("circular", "Circular"), ("decree", "Decree"), ("law", "Law"))
# Suffix a short number gets when the corpus has no matching document: decrees are always
# Government decrees, circulars default to the Ministry of Finance, and a law's
# legislative term cannot be guessed reliably from its year.
_DEFAULT_SUFFIXES = {"decree": "NĐ-CP", "circular": "TT-BTC", "law": "QH"}
_SUFFIX_PREFIXES = {"decree": "NĐ-CP", "circular": "TT", "law": "QH"}

# "..., added by Decree 359/2025 Art 1(1)": the amending provision that holds the text.
# A note without an article ("as amended by Law 149/2025") names no place to look.
_AMENDED_BY = re.compile(
    r"\b(?:added|amended|inserted|replaced) by\s+"
    r"(?P<reference>[^,;()]*?\bArt\s+\d+(?:\(\w+\))?)"
)
# "<title> [number] Art N[(clause)]" or "... Art N clause 1b"; the number may be
# "181", "181/2025", or a full "84/2025/TT-BNNMT".
_PROVISION = re.compile(
    r"^(?P<title>[^\d]*?)\s*(?P<number>\d{1,4}(?:/\d{4})?(?:/[A-ZĐ0-9-]+)?)?\s+"
    r"Art\s+(?P<article>\d+)(?:\((?P<clause>\d+[a-z]?)\)|\s+clause\s+(?P<clause_word>\w+))?"
)


@dataclass(frozen=True)
class Provision:
    label: str
    kind: str
    title: str
    number: str
    article: str
    clause: str | None
    # Amending provisions that hold the same text (an inserted clause lives in the
    # amending decree until a consolidated text exists); finding any of them counts.
    amended_by: tuple["Provision", ...] = ()


@dataclass(frozen=True)
class GoldCase:
    case_id: str
    case_type: str
    derived_from: str | None
    question: str
    as_of_date: date
    source_verified: bool
    uncertain: bool
    provisions: tuple[Provision, ...]
    unparsed: tuple[str, ...]

    @property
    def essential(self) -> tuple[Provision, ...]:
        return tuple(provision for provision in self.provisions if provision.label == "E")

    @property
    def answerable(self) -> bool:
        return bool(self.essential)

    def to_evaluation_case(self, corpus_document_numbers: Collection[str]) -> dict[str, Any]:
        """The case in the retrieval evaluation's format; only essential provisions score."""

        articles: dict[str, list[str]] = {}
        clauses: dict[str, list[list[str | None]]] = {}
        for provision in self.essential:
            number = resolve_document_number(provision, corpus_document_numbers)
            articles.setdefault(number, [])
            if provision.article not in articles[number]:
                articles[number].append(provision.article)
            clauses.setdefault(number, []).append([provision.article, provision.clause])
        supporting = {
            resolve_document_number(provision, corpus_document_numbers)
            for provision in self.provisions
            if provision.label == "S"
        }
        return {
            "case_id": self.case_id,
            "query": self.question,
            "relevant_document_numbers": list(articles),
            "relevant_articles": articles,
            "relevant_clauses": clauses,
            "essential_provisions": self._locators("E", corpus_document_numbers),
            "supporting_provisions": self._locators("S", corpus_document_numbers),
            "supporting_document_numbers": sorted(supporting - set(articles)),
            "case_type": self.case_type,
            "as_of_date": self.as_of_date.isoformat(),
            "uncertain": self.uncertain,
            "source_verified": self.source_verified,
            "unparsed_provisions": list(self.unparsed),
        }

    def _locators(
        self, label: str, corpus_document_numbers: Collection[str]
    ) -> list[list[list[str | None]]]:
        """For each distinct provision with this label, the ``[document, article, clause]``
        places that hold it: the provision itself, then any amending provision."""

        locators: list[list[list[str | None]]] = []
        for provision in self.provisions:
            if provision.label != label:
                continue
            places = [
                [
                    resolve_document_number(place, corpus_document_numbers),
                    place.article,
                    place.clause,
                ]
                for place in (provision, *provision.amended_by)
            ]
            if places not in locators:
                locators.append(places)
        return locators


def load_gold_set(path: Path) -> list[GoldCase]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [_case(row) for row in csv.DictReader(handle)]


def parse_provisions(text: str) -> tuple[tuple[Provision, ...], tuple[str, ...]]:
    """Parse a ``gold_provisions`` cell into provisions and the items it could not read.

    A reference without a number or year ("VAT Law Art 9", "Decree 181 Art 19") takes it
    from an earlier provision of the same case.
    """

    provisions: list[Provision] = []
    unparsed: list[str] = []
    for item in (part.strip() for part in text.split("|")):
        if not item or item == "(none)":
            continue
        label, _, body = item.partition(":")
        provision = _provision(label.strip().upper(), body.strip(), provisions)
        if provision is None:
            unparsed.append(item)
        else:
            provisions.append(provision)
    return tuple(provisions), tuple(unparsed)


def resolve_document_number(provision: Provision, corpus_document_numbers: Collection[str]) -> str:
    """Complete a short number ("48/2024") with the matching corpus document number."""

    if provision.number.count("/") == 2:
        return provision.number.upper()
    suffix_prefix = _SUFFIX_PREFIXES[provision.kind]
    matches = [
        number
        for number in corpus_document_numbers
        if number.upper().startswith(f"{provision.number}/")
        and number.upper().rsplit("/", 1)[-1].startswith(suffix_prefix)
    ]
    if len(matches) == 1:
        return matches[0]
    return f"{provision.number}/{_DEFAULT_SUFFIXES[provision.kind]}"


def _case(row: dict[str, str]) -> GoldCase:
    provisions, unparsed = parse_provisions(row["gold_provisions"])
    return GoldCase(
        case_id=row["case_id"].strip(),
        case_type=row["case_type"].strip(),
        derived_from=row.get("derived_from", "").strip() or None,
        question=row["question"].strip(),
        as_of_date=datetime.strptime(row["as_of_date"].strip(), "%d/%m/%Y").date(),
        source_verified=row["source_verified"].strip().upper().startswith("Y"),
        uncertain=row["uncertain"].strip().upper().startswith("Y"),
        provisions=provisions,
        unparsed=unparsed,
    )


def _provision(label: str, body: str, earlier: list[Provision]) -> Provision | None:
    if label not in {"E", "S"}:
        return None
    # The cited provision comes first; amendments and notes follow in ", ..." or " (...)".
    cited, *notes = re.split(r",\s| \(", body, maxsplit=1)
    amended_by = tuple(
        amending
        for reference in _AMENDED_BY.finditer("".join(notes))
        if (amending := _provision(label, reference.group("reference").strip(), earlier))
    )
    match = _PROVISION.match(cited)
    if match is None:
        return None
    title = match.group("title").strip()
    kind = next((kind for kind, word in _KINDS if word in title.split()), None)
    if kind is None:
        return None
    number = match.group("number") or ""
    if "/" not in number:
        number = _number_from_earlier(kind, title, number, earlier) or ""
    if not number:
        return None
    return Provision(
        label=label,
        kind=kind,
        title=title,
        number=number,
        article=match.group("article"),
        clause=match.group("clause") or match.group("clause_word"),
        amended_by=amended_by,
    )


def _number_from_earlier(
    kind: str, title: str, number: str, earlier: list[Provision]
) -> str | None:
    for provision in reversed(earlier):
        if provision.kind != kind:
            continue
        if number and provision.number.startswith(f"{number}/"):
            return provision.number
        if not number and provision.title == title:
            return provision.number
    return None
