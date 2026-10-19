import re

# Vietnamese legal document numbers:
#   31/2025/TT-BTC, 80/2021/NĐ-CP, 08/2026/VBHN-QĐ-UBND  (number/year/type-issuer)
#   48/2024/QH15, 1234/2024/NQ-UBTVQH15                 (laws and resolutions with a term)
#   18/VBHN-BTC                                         (consolidated texts without a year)
# A year-less form is only accepted for VBHN so that paths such as "12/ab-cd" and dates
# such as "31/12/2025" are not mistaken for document numbers.
DOCUMENT_NUMBER_PATTERN = re.compile(
    r"\b\d{1,4}/(?:\d{4}/[A-ZĐ]{1,10}(?:(?:-[A-ZĐ]{1,10})+\d{0,2}|\d{1,2})"
    r"|VBHN-[A-ZĐ]{1,10}(?:-[A-ZĐ]{1,10})*)\b",
    re.IGNORECASE,
)

_ISSUING_AGENCIES_BY_CODE = {
    "BTC": "Ministry of Finance",
    "CP": "Government of Vietnam",
    "TTG": "Prime Minister",
    "QH": "National Assembly",
    "UBTVQH": "National Assembly Standing Committee",
    "TCT": "General Department of Taxation",
    "TCHQ": "General Department of Customs",
    "NHNN": "State Bank of Vietnam",
}


# Cyrillic letters that look identical to Latin ones; source listings contain numbers such
# as "255/2026/NĐ-CР" with a Cyrillic "Р", which would otherwise never match.
_LOOKALIKES = str.maketrans(
    "АВСЕНІЈКМОРЅТХаеорсух", "ABCEHIJKMOPSTXaeopcyx"
)


def normalize_number_text(text: str) -> str:
    return text.translate(_LOOKALIKES)


def find_document_numbers(text: str) -> tuple[str, ...]:
    """Return distinct document numbers in order of appearance, upper-cased."""

    normalized = normalize_number_text(text).upper()
    return tuple(
        dict.fromkeys(match.group(0) for match in DOCUMENT_NUMBER_PATTERN.finditer(normalized))
    )


def issuer_code(document_number: str) -> str:
    """The issuing-body code: the last hyphen-separated part without a legislative term."""

    suffix = document_number.upper().rsplit("/", 1)[-1].rsplit("-", 1)[-1]
    return suffix.rstrip("0123456789")


def issuing_agency_for(document_number: str) -> str | None:
    return _ISSUING_AGENCIES_BY_CODE.get(issuer_code(document_number))
