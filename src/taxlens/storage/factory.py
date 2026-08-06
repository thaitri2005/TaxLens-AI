from taxlens.config import Settings, get_settings
from taxlens.storage.azure_blob import AzureBlobStorage
from taxlens.storage.base import ObjectStorage
from taxlens.storage.local import LocalObjectStorage


def get_object_storage(settings: Settings | None = None) -> ObjectStorage:
    resolved = settings or get_settings()
    if resolved.object_storage_backend == "azure_blob":
        return AzureBlobStorage(resolved)
    return LocalObjectStorage(resolved.local_storage_path)
