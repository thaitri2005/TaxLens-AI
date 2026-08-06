from pathlib import Path

from taxlens.config import Settings
from taxlens.storage.factory import get_object_storage
from taxlens.storage.local import LocalObjectStorage


def test_storage_factory_keeps_local_backend_for_local_settings(tmp_path: Path) -> None:
    storage = get_object_storage(Settings(local_storage_path=str(tmp_path)))

    assert isinstance(storage, LocalObjectStorage)
