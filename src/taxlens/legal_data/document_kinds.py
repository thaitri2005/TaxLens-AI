"""Group the recorded document types into a few kinds for browsing.

Each source records the type differently: the government portal keeps the number's
suffix (``TT-BTC``, ``NĐ-CP``, ``QH14``), the Ministry of Finance its Vietnamese name
(``Thông tư``), and the seed manifest an English code (``CIRCULAR``). The library groups
them so a reader can filter by "circular" once instead of by every spelling.
"""

import unicodedata

# Checked in order: more specific kinds first ("TTLT" before "TT", "NQ" before "QH").
_KIND_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("consolidated", ("VBHN", "VĂN BẢN HỢP NHẤT", "CONSOLIDATED")),
    ("joint_circular", ("TTLT", "THÔNG TƯ LIÊN TỊCH", "JOINT_CIRCULAR", "JOINT CIRCULAR")),
    ("circular", ("TT", "THÔNG TƯ", "CIRCULAR")),
    ("decree", ("NĐ", "ND-", "NGHỊ ĐỊNH", "DECREE")),
    ("resolution", ("NQ", "UBTVQH", "NGHỊ QUYẾT", "RESOLUTION")),
    ("law", ("QH", "LUẬT", "LAW")),
    ("ordinance", ("PL", "PHÁP LỆNH", "ORDINANCE")),
    ("decision", ("QĐ", "QD-", "QUYẾT ĐỊNH", "DECISION")),
    ("directive", ("CT", "CHỈ THỊ", "DIRECTIVE")),
)
DOCUMENT_KINDS = (*(kind for kind, _ in _KIND_MARKERS), "other")


def document_kind(document_type: str) -> str:
    value = unicodedata.normalize("NFC", document_type).strip().upper()
    for kind, markers in _KIND_MARKERS:
        if value.startswith(markers):
            return kind
    return "other"
