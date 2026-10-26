from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from purl_resolver.sbom.fixer import SbomFixOptions

logger = logging.getLogger(__name__)

OPTIONS_FILE_DEFAULT = "./data/sbom_fix_options.json"


class SbomFixOptionsStore:

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = OPTIONS_FILE_DEFAULT
        self._path = Path(path)

    def load(self) -> SbomFixOptions:
        if not self._path.exists():
            return SbomFixOptions()
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return SbomFixOptions.model_validate(data)
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
            ValidationError,
        ) as exc:
            logger.warning(
                "Failed to load sbom fix options from %s: %s", self._path, exc
            )
            return SbomFixOptions()

    def save(self, options: SbomFixOptions) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(options.model_dump(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
