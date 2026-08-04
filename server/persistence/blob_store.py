from __future__ import annotations

import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)
BLOB_PREFIX = "@@zenith-blob:"
LINES_PREFIX = "@@zenith-lines:"
STRING_THRESHOLD = 5000
LINES_THRESHOLD = 2000
LINES_CHAR_BUDGET = STRING_THRESHOLD * 4


class BlobStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_db_path(cls, db_path: str) -> BlobStore:
        return cls(Path(db_path).parent / "blobs")

    def store(self, text: str) -> str:
        blob_id = uuid.uuid4().hex
        path = self.root / f"{blob_id}.txt"
        path.write_text(text, encoding="utf-8")
        return BLOB_PREFIX + blob_id

    def load(self, pointer: str) -> str:
        if not isinstance(pointer, str) or not pointer.startswith(BLOB_PREFIX):
            return pointer
        blob_id = pointer[len(BLOB_PREFIX) :]
        path = self.root / f"{blob_id}.txt"
        if not path.exists():
            return "[blob missing]"
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("Failed to read blob %s: %s", blob_id, e)
            return "[blob unreadable]"

    def pack(self, data: object, threshold: int = STRING_THRESHOLD) -> object:
        if isinstance(data, dict):
            return {k: self.pack(v, threshold) for k, v in data.items()}
        if isinstance(data, list):
            if data and all(isinstance(x, str) for x in data):
                size = sum(len(x) + 1 for x in data)
                if len(data) > LINES_THRESHOLD or size > LINES_CHAR_BUDGET:
                    blob_id = uuid.uuid4().hex
                    (self.root / f"{blob_id}.txt").write_text("\n".join(data), encoding="utf-8")
                    return LINES_PREFIX + blob_id
            return [self.pack(v, threshold) for v in data]
        if isinstance(data, str):
            if len(data) > threshold:
                return self.store(data)
            return data
        return data

    def unpack(self, data: object) -> object:
        if isinstance(data, dict):
            return {k: self.unpack(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self.unpack(v) for v in data]
        if isinstance(data, str):
            if data.startswith(LINES_PREFIX):
                blob_id = data[len(LINES_PREFIX) :]
                path = self.root / f"{blob_id}.txt"
                if path.exists():
                    return path.read_text(encoding="utf-8", errors="replace").split("\n")
                return ["[blob missing]"]
            if data.startswith(BLOB_PREFIX):
                return self.load(data)
            return data
        return data
