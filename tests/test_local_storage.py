from pathlib import Path

import pytest

from taxlens.storage.local import LocalObjectStorage


def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)

    metadata = storage.put_bytes("raw/example.txt", b"tax document", "text/plain")

    assert metadata.size == 12
    assert storage.exists("raw/example.txt")
    assert storage.get_bytes("raw/example.txt") == b"tax document"


def test_local_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)

    with pytest.raises(ValueError, match="within the configured storage root"):
        storage.put_bytes("../outside.txt", b"unsafe")
