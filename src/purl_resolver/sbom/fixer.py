from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field, field_validator

SPEC_VERSION_PATTERN = re.compile(r"^\d+\.\d+$")
ALLOWED_SPEC_VERSIONS = {"1.6", "1.7"}

ROOT_PRIORITY: tuple[str, ...] = (
    "bomFormat",
    "specVersion",
    "serialNumber",
    "version",
    "metadata",
    "components",
    "annotations",
)

METADATA_PRIORITY: tuple[str, ...] = ("timestamp", "component")

METADATA_COMPONENT_PRIORITY: tuple[str, ...] = (
    "type",
    "name",
    "version",
    "manufacturer",
)

COMPONENT_PRIORITY: tuple[str, ...] = (
    "type",
    "name",
    "version",
    "purl",
    "externalReferences",
    "properties",
    "components",
)

ALLOWED_EXTERNAL_REFERENCE_TYPES: tuple[str, ...] = (
    "vcs",
    "source-distribution",
)

GOST_PROPERTY_PREFIX = "GOST:"

REQUIRED_GOST_PROPERTIES: tuple[tuple[str, str], ...] = (
    ("GOST:attack_surface", "no"),
    ("GOST:security_function", "no"),
)

RULE_IDS: tuple[str, ...] = (
    "root.reorder",
    "root.set_spec_version",
    "root.remove_dependencies",
    "root.remove_services",
    "root.increment_version",
    "metadata.add_timestamp",
    "metadata.reorder",
    "metadata.remove_properties",
    "metadata.remove_tools",
    "metadata_component.reorder",
    "metadata_component.remove_external_references",
    "metadata_component.remove_properties",
    "metadata_component.remove_purl",
    "metadata_component.remove_scope",
    "metadata_component.rename_supplier",
    "components.reorder",
    "components.remove_hashes",
    "components.remove_scope",
    "components.filter_external_references",
    "components.filter_properties",
    "components.fill_missing_gost_properties",
)


class RootFixOptions(BaseModel):
    reorder: bool = True
    set_spec_version: bool = True
    spec_version: str = "1.7"
    remove_dependencies: bool = True
    remove_services: bool = True
    increment_version: bool = True

    @field_validator("spec_version")
    @classmethod
    def _validate_spec_version(cls, value: str) -> str:
        if not SPEC_VERSION_PATTERN.fullmatch(value):
            raise ValueError("spec_version must match ^\\d+\\.\\d+$")
        return value


class MetadataComponentFixOptions(BaseModel):
    reorder: bool = True
    remove_external_references: bool = True
    remove_properties: bool = True
    remove_purl: bool = False
    remove_scope: bool = True
    rename_supplier: bool = True


class MetadataFixOptions(BaseModel):
    add_timestamp: bool = True
    reorder: bool = True
    remove_properties: bool = True
    remove_tools: bool = True
    component: MetadataComponentFixOptions = Field(
        default_factory=MetadataComponentFixOptions
    )


class ComponentsFixOptions(BaseModel):
    reorder: bool = True
    remove_hashes: bool = True
    remove_scope: bool = True
    filter_external_references: bool = True
    filter_properties: bool = True
    fill_missing_gost_properties: bool = False


class SbomFixOptions(BaseModel):
    root: RootFixOptions = Field(default_factory=RootFixOptions)
    metadata: MetadataFixOptions = Field(default_factory=MetadataFixOptions)
    components: ComponentsFixOptions = Field(default_factory=ComponentsFixOptions)


@dataclass
class FixStat:
    rule_id: str
    count: int


@dataclass
class FixIssue:
    code: str
    path: str
    component: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SbomFixResult:
    changed: bool
    fixed_sbom: dict
    stats: list[FixStat]
    issues: list[FixIssue]


def _rule_enabled(rule_id: str, options: SbomFixOptions) -> bool:
    if rule_id.startswith("root."):
        return getattr(options.root, rule_id.removeprefix("root."))
    if rule_id.startswith("metadata_component."):
        return getattr(
            options.metadata.component,
            rule_id.removeprefix("metadata_component."),
        )
    if rule_id.startswith("metadata."):
        return getattr(options.metadata, rule_id.removeprefix("metadata."))
    if rule_id.startswith("components."):
        return getattr(options.components, rule_id.removeprefix("components."))
    raise ValueError(f"Unknown rule id: {rule_id}")


def _enabled_rule_ids(options: SbomFixOptions) -> list[str]:
    return [rule_id for rule_id in RULE_IDS if _rule_enabled(rule_id, options)]


def _reorder(obj: dict, priority: tuple[str, ...]) -> tuple[dict, bool]:
    ordered: dict = {}
    for key in priority:
        if key in obj:
            ordered[key] = obj[key]
    for key, value in obj.items():
        if key not in ordered:
            ordered[key] = value
    return ordered, list(obj) != list(ordered)


def _reorder_in_place(obj: dict, priority: tuple[str, ...]) -> bool:
    ordered, changed = _reorder(obj, priority)
    if changed:
        obj.clear()
        obj.update(ordered)
    return changed


def _reorder_component_tree(component: dict) -> int:
    count = int(_reorder_in_place(component, COMPONENT_PRIORITY))
    nested = component.get("components")
    if isinstance(nested, list):
        for child in nested:
            if isinstance(child, dict):
                count += _reorder_component_tree(child)
    return count


def _apply_root_rules(
    data: dict,
    options: SbomFixOptions,
    counts: dict[str, int],
) -> None:
    if _rule_enabled("root.set_spec_version", options):
        target = options.root.spec_version.strip()
        counts["root.set_spec_version"] = int(data.get("specVersion") != target)
        data["specVersion"] = target

    for rule_id, key in (
        ("root.remove_dependencies", "dependencies"),
        ("root.remove_services", "services"),
    ):
        if _rule_enabled(rule_id, options):
            counts[rule_id] = int(key in data)
            data.pop(key, None)

    if _rule_enabled("root.increment_version", options):
        version = data.get("version")
        if isinstance(version, int) and not isinstance(version, bool):
            data["version"] = version + 1
            counts["root.increment_version"] = 1
        else:
            counts["root.increment_version"] = 0


def _format_timestamp(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_timestamp(metadata: dict, now: datetime) -> int:
    value = metadata.get("timestamp")
    if "timestamp" in metadata and value is not None and value != "":
        return 0
    metadata["timestamp"] = _format_timestamp(now)
    return 1


def _rename_supplier(component: dict) -> int:
    if "supplier" not in component:
        return 0
    supplier = component.pop("supplier")
    if ("manufacturer" not in component or component["manufacturer"] is None) and (
        supplier is not None
    ):
        component["manufacturer"] = supplier
    return 1


def _apply_metadata_rules(
    data: dict,
    options: SbomFixOptions,
    counts: dict[str, int],
    now: datetime,
) -> None:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return

    if _rule_enabled("metadata.add_timestamp", options):
        counts["metadata.add_timestamp"] = _add_timestamp(metadata, now)

    for rule_id, key in (
        ("metadata.remove_properties", "properties"),
        ("metadata.remove_tools", "tools"),
    ):
        if _rule_enabled(rule_id, options):
            counts[rule_id] = int(key in metadata)
            metadata.pop(key, None)

    component = metadata.get("component")
    if not isinstance(component, dict):
        return

    for rule_id, key in (
        ("metadata_component.remove_external_references", "externalReferences"),
        ("metadata_component.remove_properties", "properties"),
        ("metadata_component.remove_purl", "purl"),
        ("metadata_component.remove_scope", "scope"),
    ):
        if _rule_enabled(rule_id, options):
            counts[rule_id] = int(key in component)
            component.pop(key, None)

    if _rule_enabled("metadata_component.rename_supplier", options):
        counts["metadata_component.rename_supplier"] = _rename_supplier(component)


def _walk_components(root: dict, callback: Callable[[dict], None]) -> None:
    components = root.get("components")
    if not isinstance(components, list):
        return
    for component in components:
        if not isinstance(component, dict):
            continue
        callback(component)
        _walk_components(component, callback)


def _filter_external_references(refs: list) -> tuple[list, int]:
    kept = [
        ref
        for ref in refs
        if isinstance(ref, dict)
        and ref.get("type") in ALLOWED_EXTERNAL_REFERENCE_TYPES
    ]
    return kept, len(refs) - len(kept)


def _filter_properties(props: list) -> tuple[list, int]:
    kept = [
        prop
        for prop in props
        if isinstance(prop, dict)
        and isinstance(prop.get("name"), str)
        and prop["name"].startswith(GOST_PROPERTY_PREFIX)
    ]
    return kept, len(props) - len(kept)


def _fill_gost_properties(component: dict) -> int:
    properties = component.get("properties")
    if properties is None:
        properties = []
        component["properties"] = properties
    elif not isinstance(properties, list):
        return 0

    existing = {
        prop["name"]
        for prop in properties
        if isinstance(prop, dict) and isinstance(prop.get("name"), str)
    }
    added = 0
    for name, value in REQUIRED_GOST_PROPERTIES:
        if name not in existing:
            properties.append({"name": name, "value": value})
            added += 1
    return added


def _apply_components_rules(
    data: dict,
    options: SbomFixOptions,
    counts: dict[str, int],
) -> None:
    remove_hashes = _rule_enabled("components.remove_hashes", options)
    remove_scope = _rule_enabled("components.remove_scope", options)
    filter_external_references = _rule_enabled(
        "components.filter_external_references", options
    )
    filter_properties = _rule_enabled("components.filter_properties", options)
    fill_gost = _rule_enabled("components.fill_missing_gost_properties", options)

    def apply(component: dict) -> None:
        if remove_hashes and "hashes" in component:
            component.pop("hashes")
            counts["components.remove_hashes"] = (
                counts.get("components.remove_hashes", 0) + 1
            )

        if remove_scope and "scope" in component:
            component.pop("scope")
            counts["components.remove_scope"] = (
                counts.get("components.remove_scope", 0) + 1
            )

        external_references = component.get("externalReferences")
        if filter_external_references and isinstance(external_references, list):
            kept, removed = _filter_external_references(external_references)
            component["externalReferences"] = kept
            counts["components.filter_external_references"] = (
                counts.get("components.filter_external_references", 0) + removed
            )

        properties = component.get("properties")
        if filter_properties and isinstance(properties, list):
            kept, removed = _filter_properties(properties)
            component["properties"] = kept
            counts["components.filter_properties"] = (
                counts.get("components.filter_properties", 0) + removed
            )

        if fill_gost:
            counts["components.fill_missing_gost_properties"] = (
                counts.get("components.fill_missing_gost_properties", 0)
                + _fill_gost_properties(component)
            )

    _walk_components(data, apply)


def _apply_reorders(
    data: dict,
    options: SbomFixOptions,
    counts: dict[str, int],
) -> dict:
    if _rule_enabled("root.reorder", options):
        counts["root.reorder"] = int(_reorder_in_place(data, ROOT_PRIORITY))

    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        if _rule_enabled("metadata.reorder", options):
            counts["metadata.reorder"] = int(
                _reorder_in_place(metadata, METADATA_PRIORITY)
            )
        metadata_component = metadata.get("component")
        if isinstance(metadata_component, dict) and _rule_enabled(
            "metadata_component.reorder", options
        ):
            counts["metadata_component.reorder"] = int(
                _reorder_in_place(metadata_component, METADATA_COMPONENT_PRIORITY)
            )

    components = data.get("components")
    if isinstance(components, list) and _rule_enabled("components.reorder", options):
        counts["components.reorder"] = sum(
            _reorder_component_tree(component)
            for component in components
            if isinstance(component, dict)
        )
    return data


def fix_sbom(
    data: dict,
    options: SbomFixOptions,
    now: datetime | None = None,
) -> SbomFixResult:
    if now is None:
        now = datetime.now(timezone.utc)
    fixed_sbom = copy.deepcopy(data)
    counts: dict[str, int] = {}
    _apply_root_rules(fixed_sbom, options, counts)
    _apply_metadata_rules(fixed_sbom, options, counts, now)
    _apply_components_rules(fixed_sbom, options, counts)
    fixed_sbom = _apply_reorders(fixed_sbom, options, counts)
    stats = [
        FixStat(rule_id=rule_id, count=counts.get(rule_id, 0))
        for rule_id in _enabled_rule_ids(options)
    ]
    return SbomFixResult(
        changed=any(stat.count > 0 for stat in stats),
        fixed_sbom=fixed_sbom,
        stats=stats,
        issues=[],
    )
