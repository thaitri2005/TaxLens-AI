from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    content_type: str | None
    size: int


class ObjectStorage(Protocol):
    def put_bytes(
        self, key: str, content: bytes, content_type: str | None = None
    ) -> ObjectMetadata: ...

    def get_bytes(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def get_metadata(self, key: str) -> ObjectMetadata: ...
