from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FstecField:
    path: str
    status: Literal["mandatory", "optional"]
    condition_key: str | None = None


FSTEC_FIELDS: tuple[FstecField, ...] = (
    FstecField("root.bomFormat", "mandatory"),
    FstecField("root.specVersion", "mandatory"),
    FstecField("root.serialNumber", "optional"),
    FstecField("root.version", "mandatory"),
    FstecField("root.metadata", "mandatory"),
    FstecField("root.components", "mandatory", "componentsPresent"),
    FstecField("root.annotations", "optional"),
    FstecField("metadata.timestamp", "mandatory"),
    FstecField("metadata.component", "mandatory"),
    FstecField("metadata.component.type", "mandatory"),
    FstecField("metadata.component.name", "mandatory"),
    FstecField("metadata.component.version", "mandatory"),
    FstecField("metadata.component.manufacturer", "mandatory"),
    FstecField("metadata.component.manufacturer.name", "mandatory"),
    FstecField("components[].type", "mandatory"),
    FstecField("components[].name", "mandatory"),
    FstecField("components[].version", "mandatory"),
    FstecField("components[].purl", "mandatory"),
    FstecField("components[].cpe", "optional"),
    FstecField("components[].externalReferences", "mandatory"),
    FstecField("components[].properties", "mandatory"),
    FstecField("components[].components", "optional"),
    FstecField("components[].externalReferences[].type", "mandatory"),
    FstecField("components[].externalReferences[].url", "mandatory"),
    FstecField(
        "components[].externalReferences[].hashes", "optional", "sourceDistributionHashes"
    ),
    FstecField("components[].externalReferences[].hashes[].alg", "mandatory"),
    FstecField("components[].externalReferences[].hashes[].content", "mandatory"),
    FstecField("components[].properties[].name", "mandatory"),
    FstecField("components[].properties[].value", "mandatory"),
)

FSTEC_PATHS: frozenset[str] = frozenset(f.path for f in FSTEC_FIELDS)

DEFAULT_KEEP_FIELDS: tuple[str, ...] = (
    "metadata.tools",
    "metadata.component.properties",
    "metadata.component.group",
    "metadata.component.purl",
    "metadata.component.externalReferences",
    "metadata.component.bom-ref",
    "components[].group",
    "components[].licenses",
    "components[].description",
    "components[].bom-ref",
)

FIELD_PATH_PATTERN = re.compile(
    r"^(root|metadata|metadata\.component|components\[\])\.[A-Za-z0-9_$@.-]+$"
)
CONTEXT_ORDER = {"root": 0, "metadata": 1, "metadata.component": 2, "components[]": 3}

_CONTEXT_PREFIXES = tuple(sorted(CONTEXT_ORDER, key=len, reverse=True))


def normalize_keep(entries: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for entry in entries:
        path = entry.strip()
        if not path or path in seen:
            continue
        if FIELD_PATH_PATTERN.fullmatch(path) is None or path in FSTEC_PATHS:
            continue
        seen.add(path)
        result.append(path)
    return result


def invalid_keep_entries(entries: list[str]) -> list[str]:
    result: list[str] = []
    for entry in entries:
        path = entry.strip()
        if not path:
            continue
        if FIELD_PATH_PATTERN.fullmatch(path) is None or path in FSTEC_PATHS:
            result.append(path)
    return result


def canonical_sort_key(path: str) -> tuple[int, str]:
    for prefix in _CONTEXT_PREFIXES:
        marker = prefix + "."
        if path.startswith(marker):
            return (CONTEXT_ORDER[prefix], path[len(marker) :])
    return (len(CONTEXT_ORDER), path)
