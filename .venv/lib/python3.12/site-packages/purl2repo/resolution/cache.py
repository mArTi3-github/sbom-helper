"""Small HTTP response cache used by the resolver."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class ResponseCache:
    def __init__(self, cache_dir: str | None = None) -> None:
        self._memory: dict[str, tuple[float, Any]] = {}
        self._cache_dir = Path(cache_dir).expanduser() if cache_dir else None
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, ttl_seconds: int) -> Any | None:
        now = time.time()
        if key in self._memory:
            stored_at, value = self._memory[key]
            if now - stored_at <= ttl_seconds:
                return value
            del self._memory[key]

        if not self._cache_dir:
            return None
        path = self._path_for_key(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if now - float(payload.get("stored_at", 0)) > ttl_seconds:
            return None
        return payload.get("value")

    def set(self, key: str, value: Any) -> None:
        stored = (time.time(), value)
        self._memory[key] = stored
        if not self._cache_dir:
            return
        path = self._path_for_key(key)
        payload = {"stored_at": stored[0], "value": value}
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _path_for_key(self, key: str) -> Path:
        if self._cache_dir is None:
            raise RuntimeError("Cache directory is not configured.")
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.json"
