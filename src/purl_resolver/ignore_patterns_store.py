from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PATTERNS_FILE_DEFAULT = "./data/sbom_components_ignore_patterns.json"


class IgnorePatternsStore:

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = PATTERNS_FILE_DEFAULT
        self._path = Path(path)

    def load(self) -> list[dict[str, str]]:
        if not self._path.exists():
            return []
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                return []
            result: list[dict[str, str]] = []
            for item in data:
                if isinstance(item, dict):
                    cleaned = {str(k): str(v) for k, v in item.items() if isinstance(v, (str, int, float, bool))}
                    result.append(cleaned)
            return result
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load ignore patterns from %s: %s", self._path, exc)
            return []

    def save(self, patterns: list[dict[str, str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(patterns, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
