from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from taxlens.config import Settings
from taxlens.storage.base import ObjectMetadata


class AzureBlobStorage:
    def __init__(self, settings: Settings) -> None:
        try:
            identity = import_module("azure.identity")
            blob = import_module("azure.storage.blob")
        except ImportError as error:
            raise RuntimeError(
                "Azure Blob storage requires the optional cloud dependencies"
            ) from error

        if settings.azure_storage_connection_string:
            self._client = blob.BlobServiceClient.from_connection_string(
                settings.azure_storage_connection_string
            )
        elif settings.azure_storage_account_url:
            self._client = blob.BlobServiceClient(
                account_url=settings.azure_storage_account_url,
                credential=identity.DefaultAzureCredential(),
            )
        else:
            raise RuntimeError(
                "AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL is required"
            )
        self._container = self._client.get_container_client(settings.azure_storage_container)

    def put_bytes(
        self, key: str, content: bytes, content_type: str | None = None
    ) -> ObjectMetadata:
        blob = self._container.get_blob_client(key)
        headers: dict[str, str] = {}
        if content_type:
            headers["content_type"] = content_type
        blob.upload_blob(content, overwrite=True, content_settings=_content_settings(headers))
        return ObjectMetadata(key=key, content_type=content_type, size=len(content))

    def get_bytes(self, key: str) -> bytes:
        return cast(bytes, self._container.get_blob_client(key).download_blob().readall())

    def exists(self, key: str) -> bool:
        try:
            self._container.get_blob_client(key).get_blob_properties()
        except Exception as error:
            if _is_not_found(error):
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        self._container.get_blob_client(key).delete_blob(delete_snapshots="include")

    def get_metadata(self, key: str) -> ObjectMetadata:
        properties = self._container.get_blob_client(key).get_blob_properties()
        return ObjectMetadata(
            key=key,
            content_type=properties.content_settings.content_type,
            size=properties.size,
        )


def _content_settings(headers: dict[str, str]) -> Any:
    ContentSettings = import_module("azure.storage.blob").ContentSettings

    return ContentSettings(content_type=headers.get("content_type"))


def _is_not_found(error: Exception) -> bool:
    return getattr(error, "status_code", None) == 404
