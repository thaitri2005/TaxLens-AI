from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    content_type: str | None
    size: int


class LocalObjectStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put_bytes(
        self, key: str, content: bytes, content_type: str | None = None
    ) -> ObjectMetadata:
        target = self._resolve_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return ObjectMetadata(key=key, content_type=content_type, size=len(content))

    def get_bytes(self, key: str) -> bytes:
        return self._resolve_key(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve_key(key).is_file()

    def delete(self, key: str) -> None:
        target = self._resolve_key(key)
        if target.exists():
            target.unlink()

    def get_metadata(self, key: str) -> ObjectMetadata:
        target = self._resolve_key(key)
        return ObjectMetadata(key=key, content_type=None, size=target.stat().st_size)

    def _resolve_key(self, key: str) -> Path:
        target = (self.root / key).resolve()
        root = self.root.resolve()
        if root != target and root not in target.parents:
            raise ValueError("Object key must remain within the configured storage root")
        return target
