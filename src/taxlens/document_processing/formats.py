"""Text extraction for word-processor documents: Word 97-2003, RTF, and DOCX.

Official sources publish many historical documents as Word files. Their text is exact, so
reading them avoids OCR (minutes per scanned document) and its recognition errors. The
format is detected from the content, not the file name: files named ``.doc`` are often
RTF. Legacy TCVN3 text is converted to Unicode.
"""

import re
import struct
import zipfile
from io import BytesIO
from xml.etree import ElementTree

from taxlens.document_processing.legacy_text import convert_tcvn3

OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
RTF_SIGNATURE = b"{\\rtf"
ZIP_SIGNATURE = b"PK\x03\x04"


def detect_format(content: bytes) -> str:
    if content.startswith(b"%PDF"):
        return "pdf"
    if content.startswith(OLE_SIGNATURE):
        return "doc"
    if content.lstrip()[:5] == RTF_SIGNATURE:
        return "rtf"
    if content.startswith(ZIP_SIGNATURE):
        return "docx"
    return "text"


def extract_word_processor_text(content: bytes) -> str:
    """Extract text from a Word 97-2003, RTF, or DOCX file; raises ValueError otherwise."""

    document_format = detect_format(content)
    if document_format == "doc":
        text = _word97_text(content)
    elif document_format == "rtf":
        text = _rtf_text(content)
    elif document_format == "docx":
        text = _docx_text(content)
    else:
        raise ValueError(f"Not a word-processor document: {document_format}")
    return convert_tcvn3(text)


# Word 97-2003 binary format: the text is described by the piece table in the CLX
# structure of the table stream ([MS-DOC] 2.4.1).
_FIB_FLAGS_OFFSET = 0x0A
_FIB_CCP_TEXT_OFFSET = 0x4C
_FIB_FC_CLX_OFFSET = 0x01A2
_WHICH_TABLE_STREAM = 0x0200
_FIELD_BEGIN, _FIELD_SEPARATOR, _FIELD_END = "\x13", "\x14", "\x15"


def _word97_text(content: bytes) -> str:
    import olefile  # type: ignore[import-untyped]

    with olefile.OleFileIO(BytesIO(content)) as ole:
        if not ole.exists("WordDocument"):
            raise ValueError("OLE file is not a Word document")
        word = ole.openstream("WordDocument").read()
        flags = struct.unpack_from("<H", word, _FIB_FLAGS_OFFSET)[0]
        table_name = "1Table" if flags & _WHICH_TABLE_STREAM else "0Table"
        if not ole.exists(table_name):
            raise ValueError("Word table stream is missing")
        table = ole.openstream(table_name).read()
    main_text_length = struct.unpack_from("<I", word, _FIB_CCP_TEXT_OFFSET)[0]
    clx_offset, clx_length = struct.unpack_from("<II", word, _FIB_FC_CLX_OFFSET)
    if clx_length == 0 or clx_offset + clx_length > len(table):
        raise ValueError("Word piece table not found (encrypted or unsupported file)")
    text = "".join(_word97_pieces(word, table[clx_offset : clx_offset + clx_length]))
    return _clean_word_text(text[:main_text_length])


def _word97_pieces(word: bytes, clx: bytes) -> list[str]:
    position = 0
    while position < len(clx) and clx[position] == 0x01:  # skip Prc (formatting) records
        position += 3 + struct.unpack_from("<H", clx, position + 1)[0]
    if position >= len(clx) or clx[position] != 0x02:
        raise ValueError("Word piece table is malformed")
    table_length = struct.unpack_from("<I", clx, position + 1)[0]
    plc = clx[position + 5 : position + 5 + table_length]
    piece_count = (len(plc) - 4) // 12
    positions = struct.unpack_from(f"<{piece_count + 1}I", plc, 0)
    pieces: list[str] = []
    for index in range(piece_count):
        descriptor = 4 * (piece_count + 1) + 8 * index
        file_offset = struct.unpack_from("<I", plc, descriptor + 2)[0]
        characters = positions[index + 1] - positions[index]
        if file_offset & 0x40000000:
            # Compressed piece: one byte per character, Windows-1252 (or legacy TCVN3).
            start = (file_offset & ~0x40000000) // 2
            pieces.append(word[start : start + characters].decode("cp1252", errors="replace"))
        else:
            pieces.append(
                word[file_offset : file_offset + 2 * characters].decode(
                    "utf-16-le", errors="replace"
                )
            )
    return pieces


def _clean_word_text(text: str) -> str:
    # Field codes (between begin and separator) are instructions such as PAGE or HYPERLINK;
    # only the field results are document text.
    output: list[str] = []
    in_code: list[bool] = []
    for character in text:
        if character == _FIELD_BEGIN:
            in_code.append(True)
        elif character == _FIELD_SEPARATOR and in_code:
            in_code[-1] = False
        elif character == _FIELD_END and in_code:
            in_code.pop()
        elif not (in_code and in_code[-1]):
            output.append(character)
    cleaned = "".join(output)
    cleaned = cleaned.replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    cleaned = cleaned.replace("\x07", "\n")  # table cell and row ends
    return re.sub(r"[\x00-\x08\x0e-\x1f]", "", cleaned)


# RTF: destinations whose content is not document text.
_RTF_SKIPPED_DESTINATIONS = frozenset(
    {
        "fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "themedata",
        "colorschememapping", "latentstyles", "datastore", "xmlnstbl", "listtable",
        "listoverridetable", "rsidtbl", "generator", "header", "headerl", "headerr",
        "headerf", "footer", "footerl", "footerr", "footerf", "fldinst", "filetbl",
        "revtbl", "pgdsctbl", "mmathPr", "wgrffmtfilter", "bkmkstart", "bkmkend",
    }
)
_RTF_TOKEN = re.compile(
    r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\([^a-zA-Z])|([{}])|([^\\{}\r\n]+)|[\r\n]+"
)


# RTF \fcharset values -> Python codecs. Charset 0 keeps byte values (Latin-1) so legacy
# TCVN3 text in ".VnTime" fonts survives for conversion; 163 is the Windows Vietnamese
# code page, which writes some letters as base letter + combining tone mark.
_RTF_CHARSET_CODECS = {
    0: "latin-1", 163: "cp1258", 238: "cp1250", 204: "cp1251", 161: "cp1253",
    162: "cp1254", 177: "cp1255", 178: "cp1256", 186: "cp1257", 222: "cp874",
}
_RTF_FONT_CHARSET = re.compile(r"\{\\f(\d+)[^{}]*?\\fcharset(\d+)")


def _rtf_text(content: bytes) -> str:
    source = content.decode("latin-1")
    font_codecs = {
        int(font): _RTF_CHARSET_CODECS.get(int(charset), "cp1252")
        for font, charset in _RTF_FONT_CHARSET.findall(source)
    }
    default_font = re.search(r"\\deff(\d+)", source[:500])
    output: list[str] = []
    pending_bytes = bytearray()
    font = int(default_font.group(1)) if default_font else 0
    stack: list[tuple[bool, int, int]] = []
    skipping = False
    unicode_skip = 1
    pending_skip = 0

    def flush() -> None:
        if pending_bytes:
            codec = font_codecs.get(font, "cp1252")
            output.append(bytes(pending_bytes).decode(codec, errors="replace"))
            pending_bytes.clear()

    for match in _RTF_TOKEN.finditer(source):
        word, argument, hex_byte, symbol, brace, text = match.groups()
        if hex_byte is None:
            flush()
        if brace == "{":
            stack.append((skipping, unicode_skip, font))
            continue
        if brace == "}":
            skipping, unicode_skip, font = stack.pop() if stack else (False, 1, font)
            continue
        if pending_skip and (text or hex_byte):
            # Characters after \uN are its ANSI fallback and must be dropped.
            if text:
                dropped = min(pending_skip, len(text))
                text = text[dropped:]
                pending_skip -= dropped
            else:
                pending_skip -= 1
                continue
        if word is not None:
            if word in _RTF_SKIPPED_DESTINATIONS:
                skipping = True
            elif skipping:
                continue
            elif word == "f" and argument is not None:
                font = int(argument)
            elif word in ("par", "line", "row", "cell", "sect", "page"):
                output.append("\n")
            elif word == "tab":
                output.append("\t")
            elif word == "uc" and argument is not None:
                unicode_skip = int(argument)
            elif word == "u" and argument is not None:
                code = int(argument)
                output.append(chr(code + 65536 if code < 0 else code))
                pending_skip = unicode_skip
            continue
        if symbol is not None:
            if symbol == "*":
                skipping = True
            elif not skipping and symbol in "\\{}":
                output.append(symbol)
            elif not skipping and symbol == "~":
                output.append(" ")
            continue
        if skipping:
            continue
        if hex_byte is not None:
            # Bytes are decoded together so multi-byte and combining sequences stay intact.
            pending_bytes.append(int(hex_byte, 16))
        elif text:
            output.append(text)
    flush()
    return "".join(output)


_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError("Not a DOCX document") from error
    root = ElementTree.fromstring(xml)
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{_WORD_NAMESPACE}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{_WORD_NAMESPACE}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_WORD_NAMESPACE}tab":
                parts.append("\t")
            elif node.tag in (f"{_WORD_NAMESPACE}br", f"{_WORD_NAMESPACE}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)
