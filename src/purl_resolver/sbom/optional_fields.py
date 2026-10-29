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
_MISSING = object()


def normalize_keep(entries: list[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            continue
        path = entry.strip()
        if not path or path in seen:
            continue
        if FIELD_PATH_PATTERN.fullmatch(path) is None or path in FSTEC_PATHS:
            continue
        seen.add(path)
        result.append(path)
    return result


def invalid_keep_entries(entries: list[object]) -> list[str]:
    result: list[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            result.append(str(entry))
            continue
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


_FSTEC_STATUS: dict[str, str] = {field.path: field.status for field in FSTEC_FIELDS}


@dataclass(frozen=True)
class FieldInfo:
    path: str
    status: str
    count: int


def _split_path(path: str) -> tuple[str, str] | None:
    for prefix in _CONTEXT_PREFIXES:
        marker = prefix + "."
        if path.startswith(marker):
            return prefix, path[len(marker) :]
    return None


def _iter_components(value: object):
    if not isinstance(value, list):
        return
    for item in value:
        if isinstance(item, dict):
            yield item
            yield from _iter_components(item.get("components"))


def analyze_fields(data: dict) -> list[FieldInfo]:
    counts: dict[str, int] = {}

    def collect(prefix: str, obj: dict) -> None:
        for key in obj:
            path = f"{prefix}.{key}"
            if FIELD_PATH_PATTERN.fullmatch(path) is not None:
                counts[path] = counts.get(path, 0) + 1

    if isinstance(data, dict):
        collect("root", data)

    metadata = data.get("metadata") if isinstance(data, dict) else None
    if isinstance(metadata, dict):
        collect("metadata", metadata)
        component = metadata.get("component")
        if isinstance(component, dict):
            collect("metadata.component", component)

    if isinstance(data, dict):
        for item in _iter_components(data.get("components")):
            collect("components[]", item)

    return [
        FieldInfo(path=path, status=_FSTEC_STATUS.get(path, "additional"), count=count)
        for path, count in sorted(counts.items(), key=lambda item: canonical_sort_key(item[0]))
    ]


def remove_optional_fields(
    data: dict, paths: list[str], keep: list[str]
) -> dict[str, int]:
    keep_set = set(normalize_keep(keep))
    accepted: list[str] = []
    seen: set[str] = set()
    for entry in paths:
        path = entry.strip()
        if not path or path in seen:
            continue
        if FIELD_PATH_PATTERN.fullmatch(path) is None or path in FSTEC_PATHS:
            continue
        if path in keep_set:
            continue
        seen.add(path)
        accepted.append(path)
    accepted.sort(key=canonical_sort_key)

    counts: dict[str, int] = {}
    for path in accepted:
        split = _split_path(path)
        if split is None:
            continue
        context, field = split
        if context == "root":
            counts[path] = 0
            if isinstance(data, dict) and data.pop(field, _MISSING) is not _MISSING:
                counts[path] = 1
        elif context == "metadata":
            metadata = data.get("metadata") if isinstance(data, dict) else None
            counts[path] = (
                1
                if isinstance(metadata, dict) and metadata.pop(field, _MISSING) is not _MISSING
                else 0
            )
        elif context == "metadata.component":
            metadata = data.get("metadata") if isinstance(data, dict) else None
            component = metadata.get("component") if isinstance(metadata, dict) else None
            counts[path] = (
                1
                if isinstance(component, dict) and component.pop(field, _MISSING) is not _MISSING
                else 0
            )
        else:
            removed = 0
            root_components = data.get("components") if isinstance(data, dict) else None
            for item in _iter_components(root_components):
                if item.pop(field, _MISSING) is not _MISSING:
                    removed += 1
            counts[path] = removed
    return counts
