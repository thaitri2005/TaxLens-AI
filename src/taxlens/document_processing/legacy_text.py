"""Convert pre-Unicode Vietnamese text (TCVN3 / ABC encoding) to Unicode.

Government documents written before about 2005 often use the ``.VnTime`` family of fonts,
which store each Vietnamese letter as a single byte in the Latin-1 range. Read as Latin-1
or Windows-1252, "Thông tư" appears as "Th«ng t­". Lines dominated by these bytes are
converted; lines that already contain Unicode Vietnamese are left alone, so documents that
mix encodings are handled line by line.
"""

import re

# Byte value (as a Latin-1 code point) -> Unicode character, TCVN3 (ABC) encoding.
_TCVN3 = {
    0xA1: "Ă", 0xA2: "Â", 0xA3: "Ê", 0xA4: "Ô", 0xA5: "Ơ", 0xA6: "Ư", 0xA7: "Đ",
    0xA8: "ă", 0xA9: "â", 0xAA: "ê", 0xAB: "ô", 0xAC: "ơ", 0xAD: "ư", 0xAE: "đ",
    0xB5: "à", 0xB6: "ả", 0xB7: "ã", 0xB8: "á", 0xB9: "ạ",
    0xBB: "ằ", 0xBC: "ẳ", 0xBD: "ẵ", 0xBE: "ắ", 0xC6: "ặ",
    0xC7: "ầ", 0xC8: "ẩ", 0xC9: "ẫ", 0xCA: "ấ", 0xCB: "ậ",
    0xCC: "è", 0xCE: "ẻ", 0xCF: "ẽ", 0xD0: "é", 0xD1: "ẹ",
    0xD2: "ề", 0xD3: "ể", 0xD4: "ễ", 0xD5: "ế", 0xD6: "ệ",
    0xD7: "ì", 0xD8: "ỉ", 0xDC: "ĩ", 0xDD: "í", 0xDE: "ị",
    0xDF: "ò", 0xE1: "ỏ", 0xE2: "õ", 0xE3: "ó", 0xE4: "ọ",
    0xE5: "ồ", 0xE6: "ổ", 0xE7: "ỗ", 0xE8: "ố", 0xE9: "ộ",
    0xEA: "ờ", 0xEB: "ở", 0xEC: "ỡ", 0xED: "ớ", 0xEE: "ợ",
    0xEF: "ù", 0xF1: "ủ", 0xF2: "ũ", 0xF3: "ú", 0xF4: "ụ",
    0xF5: "ừ", 0xF6: "ử", 0xF7: "ữ", 0xF8: "ứ", 0xF9: "ự",
    0xFA: "ỳ", 0xFB: "ỷ", 0xFC: "ỹ", 0xFD: "ý", 0xFE: "ỵ",
}
_TCVN3_TABLE = {code: character for code, character in _TCVN3.items()}
# Letters that Unicode Vietnamese stores in the Latin-1 range. TCVN3 uses the same bytes for
# other letters: "ê" is "ờ", "ô" is "ụ", and "â" is "õ". They say nothing about the encoding.
_SHARED_WITH_UNICODE = frozenset("áâãèéêìíòóôõùúýÈÉÊÌÒÓÔÕÝ")
_TCVN3_MARKERS = frozenset(chr(code) for code in _TCVN3)
_TCVN3_ONLY = _TCVN3_MARKERS - _SHARED_WITH_UNICODE
# Used as quotation marks in Unicode text, so they count only inside a word.
_QUOTES = frozenset("«»")
# Ordinary symbols in Unicode text, so one alone does not prove a word is TCVN3.
_SYMBOLS = frozenset("×§©®")
MIN_LEGACY_SHARE = 0.1
# Vietnamese letters outside Latin-1, which TCVN3 text cannot contain.
_UNICODE_VIETNAMESE = re.compile(r"[ăđĩũơưĂĐĨŨƠƯẠ-ỹ]")
_WORD = re.compile(r"\S+")


def _tcvn3_only_letters(text: str) -> int:
    """TCVN3-only characters touching a letter, so "§ 2" and "3 × 4" do not count."""

    count = 0
    for index, character in enumerate(text):
        if character not in _TCVN3_ONLY:
            continue
        before = index > 0 and _is_letter(text[index - 1])
        after = index + 1 < len(text) and _is_letter(text[index + 1])
        if (before and after) if character in _QUOTES else (before or after):
            count += 1
    return count


def _is_letter(character: str) -> bool:
    return character.isalpha()


def looks_like_tcvn3(line: str) -> bool:
    """True when the line itself proves it is TCVN3."""

    if _UNICODE_VIETNAMESE.search(line):
        return False
    only = _tcvn3_only_letters(line)
    shared = sum(character in _SHARED_WITH_UNICODE for character in line)
    return only >= 2 or (only == 1 and shared >= 1)


def convert_tcvn3(text: str) -> str:
    """Convert TCVN3 text to Unicode, leaving Unicode and plain ASCII text unchanged.

    A line such as "Bé" cannot be judged alone, so it follows the nearest line that can be.
    Within a Unicode line, only words that prove to be TCVN3 are converted.
    """

    lines = text.split(chr(10))
    verdicts = [_verdict(line) for line in lines]
    legacy_lines = verdicts.count(True)
    # OCR noise such as "trực ti¢p" proves a line or two; TCVN3 text proves many.
    if legacy_lines < MIN_LEGACY_SHARE * (legacy_lines + verdicts.count(False)) or not legacy_lines:
        return text
    settled = _nearest_verdicts(verdicts)
    converted: list[str] = []
    for line, verdict, nearest in zip(lines, verdicts, settled, strict=True):
        if verdict is False:
            converted.append(_convert_words(line))
        elif nearest and any(character in _TCVN3_MARKERS for character in line):
            converted.append(_convert_line(line))
        else:
            converted.append(line)
    return chr(10).join(converted)


def has_legacy_text(text: str) -> bool:
    return convert_tcvn3(text) != text


def _verdict(line: str) -> bool | None:
    """True for TCVN3, False for Unicode Vietnamese, None when the line cannot tell."""

    if _UNICODE_VIETNAMESE.search(line):
        return False
    return True if looks_like_tcvn3(line) else None


def _nearest_verdicts(verdicts: list[bool | None]) -> list[bool]:
    """Each line's own verdict, or that of the nearest line that has one."""

    distance_and_verdict: list[tuple[int, bool] | None] = [None] * len(verdicts)
    for order in (range(len(verdicts)), range(len(verdicts) - 1, -1, -1)):
        latest: tuple[int, bool] | None = None
        for index in order:
            verdict = verdicts[index]
            if verdict is not None:
                latest = (index, verdict)
            if latest is None:
                continue
            distance = abs(index - latest[0])
            current = distance_and_verdict[index]
            if current is None or distance < current[0]:
                distance_and_verdict[index] = (distance, latest[1])
    return [item is not None and item[1] for item in distance_and_verdict]


def _convert_words(line: str) -> str:
    return _WORD.sub(lambda match: _converted_word(match.group(0)), line)


def _converted_word(word: str) -> str:
    only = _tcvn3_only_letters(word)
    symbol_alone = only == 1 and any(character in _SYMBOLS for character in word)
    if only and not symbol_alone and not _UNICODE_VIETNAMESE.search(word):
        return _convert_line(word)
    return word


def _convert_line(line: str) -> str:
    converted = line.translate(_TCVN3_TABLE)
    # Headings use the uppercase ``.VnTimeH`` font, which reuses the lowercase byte codes:
    # "TH«NG T­" becomes "THôNG Tư". Words whose plain letters are all uppercase are
    # restored to uppercase.
    return _WORD.sub(_restore_uppercase, converted)


def _restore_uppercase(match: re.Match[str]) -> str:
    word = match.group(0)
    ascii_letters = [character for character in word if character.isascii() and character.isalpha()]
    # Two or more plain letters, so a capitalized word such as "Hà" stays as it is.
    if len(ascii_letters) >= 2 and all(character.isupper() for character in ascii_letters):
        return word.upper()
    return word
