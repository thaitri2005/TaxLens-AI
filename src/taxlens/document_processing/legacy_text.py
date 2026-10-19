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
_TCVN3_MARKERS = frozenset(chr(code) for code in _TCVN3)
_UNICODE_VIETNAMESE = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯẠ-ỹ]")
_WORD = re.compile(r"\S+")


def looks_like_tcvn3(line: str) -> bool:
    markers = sum(character in _TCVN3_MARKERS for character in line)
    return markers >= 2 and not _UNICODE_VIETNAMESE.search(line)


def convert_tcvn3(text: str) -> str:
    """Convert TCVN3 lines to Unicode, leaving Unicode and plain ASCII lines unchanged."""

    return "\n".join(
        _convert_line(line) if looks_like_tcvn3(line) else line for line in text.split("\n")
    )


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
