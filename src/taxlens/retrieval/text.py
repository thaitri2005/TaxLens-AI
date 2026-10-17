"""Text normalization shared by indexing and query processing."""

import unicodedata

# Precomposed Vietnamese letters and their unaccented forms. Migration 20261017_0005 uses the
# same pair with PostgreSQL translate() to build the folded search vector, and a test keeps
# them identical.
VIETNAMESE_ACCENTED = (
    "AàÀáÁãÃảẢạẠăĂằẰắẮẵẴẳẲặẶâÂầẦấẤẫẪẩẨậẬEèÈéÉẽẼẻẺẹẸêÊềỀếẾễỄểỂệỆIìÌíÍĩĨỉỈịỊOòÒóÓõÕỏỎọỌôÔồỒốỐỗỖổỔộỘ"
    "ơƠờỜớỚỡỠởỞợỢUùÙúÚũŨủỦụỤưƯừỪứỨữỮửỬựỰYỳỲýÝỹỸỷỶỵỴđĐ"
)
VIETNAMESE_UNACCENTED = (
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaeeeeeeeeeeeeeeeeeeeeeeeiiiiiiiiiiioooooooooooooooooooooo"
    "ooooooooooooouuuuuuuuuuuuuuuuuuuuuuuyyyyyyyyyyydd"
)
_FOLD_TABLE = str.maketrans(VIETNAMESE_ACCENTED, VIETNAMESE_UNACCENTED)


def fold_vietnamese(text: str) -> str:
    """Remove Vietnamese diacritics so "hóa đơn", "hoa don" and OCR's "hóa don" all match."""

    return unicodedata.normalize("NFC", text).translate(_FOLD_TABLE)
