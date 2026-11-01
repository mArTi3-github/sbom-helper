from __future__ import annotations

import copy
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field, field_validator

from .optional_fields import DEFAULT_KEEP_FIELDS, normalize_keep, remove_optional_fields

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
    "reorder",
    "set_spec_version",
    "increment_version",
    "add_timestamp",
    "add_manufacturer",
    "components.filter_external_references",
    "components.filter_properties",
    "components.fill_missing_gost_properties",
    "licenses.filter_non_proprietary",
    "licenses.add_proprietary",
    "licenses.remove_proprietary_source_references",
)


class ComponentsFixOptions(BaseModel):
    filter_external_references: bool = True
    filter_properties: bool = True
    fill_missing_gost_properties: bool = False


class LicensePatternItem(BaseModel):
    field: str = ""
    pattern: str = ""


class LicensesFixOptions(BaseModel):
    filter_non_proprietary: bool = False
    add_proprietary: bool = False
    remove_proprietary_source_references: bool = False
    add_patterns: list[LicensePatternItem] = Field(default_factory=list)


class OptionalFieldsFixOptions(BaseModel):
    keep: list[str] = Field(default_factory=lambda: list(DEFAULT_KEEP_FIELDS))

    @field_validator("keep", mode="before")
    @classmethod
    def _validate_keep(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("keep must be a list of field paths")
        return normalize_keep(value)


class SbomFixOptions(BaseModel):
    reorder: bool = True
    set_spec_version: bool = True
    spec_version: str = "1.7"
    increment_version: bool = True
    add_timestamp: bool = True
    add_manufacturer: bool = True
    manufacturer: str = "Positive Technologies"
    components: ComponentsFixOptions = Field(default_factory=ComponentsFixOptions)
    licenses: LicensesFixOptions = Field(default_factory=LicensesFixOptions)
    optional_fields: OptionalFieldsFixOptions = Field(default_factory=OptionalFieldsFixOptions)

    @field_validator("spec_version", mode="before")
    @classmethod
    def _validate_spec_version(cls, value: object) -> str:
        if isinstance(value, str):
            value = value.strip()
        if not isinstance(value, str) or not SPEC_VERSION_PATTERN.fullmatch(value):
            raise ValueError("spec_version must match ^\\d+\\.\\d+$")
        return value

    @field_validator("manufacturer", mode="before")
    @classmethod
    def _validate_manufacturer(cls, value: object) -> str:
        if isinstance(value, str):
            value = value.strip()
        if not isinstance(value, str) or not value:
            raise ValueError("manufacturer must be a non-empty string")
        return value


@dataclass
class FixStat:
    rule_id: str
    count: int
    field: str | None = None


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
    prefix, _, name = rule_id.partition(".")
    if prefix == "components":
        return getattr(options.components, name)
    if prefix == "licenses":
        return getattr(options.licenses, name)
    return getattr(options, rule_id)


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
    if _rule_enabled("set_spec_version", options):
        target = options.spec_version.strip()
        counts["set_spec_version"] = int(data.get("specVersion") != target)
        data["specVersion"] = target

    if _rule_enabled("increment_version", options):
        version = data.get("version")
        if isinstance(version, int) and not isinstance(version, bool):
            data["version"] = version + 1
            counts["increment_version"] = 1
        else:
            counts["increment_version"] = 0


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


def _add_manufacturer(component: dict, value: str) -> int:
    manufacturer = component.get("manufacturer")
    if isinstance(manufacturer, dict):
        name = manufacturer.get("name")
        if isinstance(name, str) and name.strip():
            return 0
    component["manufacturer"] = {"name": value}
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

    if _rule_enabled("add_timestamp", options):
        counts["add_timestamp"] = _add_timestamp(metadata, now)

    component = metadata.get("component")
    if not isinstance(component, dict):
        return

    if _rule_enabled("add_manufacturer", options):
        counts["add_manufacturer"] = _add_manufacturer(
            component, options.manufacturer
        )


def _walk_components(root: dict, callback: Callable[[dict], None]) -> None:
    components = root.get("components")
    if not isinstance(components, list):
        return
    for component in components:
        if not isinstance(component, dict):
            continue
        callback(component)
        _walk_components(component, callback)


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _missing_gost_names(properties: list) -> list[str]:
    present = {
        prop["name"]
        for prop in properties
        if isinstance(prop, dict) and isinstance(prop.get("name"), str)
    }
    return [name for name, _ in REQUIRED_GOST_PROPERTIES if name not in present]


def _has_source_reference(component: dict) -> bool:
    references = component.get("externalReferences")
    if not isinstance(references, list):
        return False
    return any(
        isinstance(reference, dict)
        and reference.get("type") in ALLOWED_EXTERNAL_REFERENCE_TYPES
        for reference in references
    )


def _is_source_reference_exempt(component: dict) -> bool:
    components = component.get("components")
    if isinstance(components, list) and components:
        return True

    properties = component.get("properties")
    if isinstance(properties, list):
        for prop in properties:
            if (
                isinstance(prop, dict)
                and prop.get("name") == "GOST:provided_by"
                and _is_non_empty_string(prop.get("value"))
            ):
                return True

    licenses = component.get("licenses")
    if isinstance(licenses, list):
        for entry in licenses:
            if not isinstance(entry, dict):
                continue
            license_info = entry.get("license")
            if (
                isinstance(license_info, dict)
                and license_info.get("name") == "Proprietary"
            ):
                return True

    return False


def _collect_component_issues(
    components: list,
    base_path: str,
    issues: list[FixIssue],
) -> None:
    if not isinstance(components, list):
        return
    for index, component in enumerate(components):
        path = f"{base_path}[{index}]"
        if not isinstance(component, dict):
            issues.append(FixIssue(code="component.invalid_entry", path=path))
            continue

        name = component.get("name")
        component_name = name if _is_non_empty_string(name) else None
        for field_name, code in (
            ("type", "component.missing_type"),
            ("name", "component.missing_name"),
            ("version", "component.missing_version"),
            ("purl", "component.missing_purl"),
        ):
            if not _is_non_empty_string(component.get(field_name)):
                issues.append(
                    FixIssue(code=code, path=path, component=component_name)
                )

        properties = component.get("properties")
        if properties is not None and not isinstance(properties, list):
            issues.append(
                FixIssue(
                    code="component.invalid_properties",
                    path=path,
                    component=component_name,
                )
            )
        else:
            missing = _missing_gost_names(
                properties if isinstance(properties, list) else []
            )
            if missing:
                issues.append(
                    FixIssue(
                        code="component.missing_gost_properties",
                        path=path,
                        component=component_name,
                        details={"missing": missing},
                    )
                )

        external_references = component.get("externalReferences")
        if external_references is not None and not isinstance(
            external_references, list
        ):
            issues.append(
                FixIssue(
                    code="component.invalid_external_references",
                    path=path,
                    component=component_name,
                )
            )
        elif not _has_source_reference(component) and not _is_source_reference_exempt(
            component
        ):
            issues.append(
                FixIssue(
                    code="component.missing_source_reference",
                    path=path,
                    component=component_name,
                )
            )

        nested = component.get("components")
        if nested is not None and not isinstance(nested, list):
            issues.append(
                FixIssue(
                    code="component.invalid_subcomponents",
                    path=path,
                    component=component_name,
                )
            )
            continue

        if isinstance(nested, list):
            _collect_component_issues(nested, f"{path}.components", issues)


def _collect_root_issues(data: dict, issues: list[FixIssue]) -> None:
    spec_version = data.get("specVersion")
    if "specVersion" not in data or spec_version is None or spec_version == "":
        issues.append(FixIssue(code="root.missing_spec_version", path="$"))
    elif not isinstance(spec_version, str):
        issues.append(FixIssue(code="root.invalid_spec_version", path="$"))
    elif spec_version not in ALLOWED_SPEC_VERSIONS:
        issues.append(FixIssue(code="root.spec_version_not_allowed", path="$"))

    version = data.get("version")
    if "version" not in data or version is None:
        issues.append(FixIssue(code="root.missing_version", path="$"))
    elif not isinstance(version, int) or isinstance(version, bool):
        issues.append(FixIssue(code="root.invalid_version", path="$"))

    metadata = data.get("metadata")
    if "metadata" not in data or metadata is None:
        issues.append(FixIssue(code="root.missing_metadata", path="$"))
    elif not isinstance(metadata, dict):
        issues.append(FixIssue(code="root.invalid_metadata", path="$"))

    components = data.get("components")
    if (
        "components" in data
        and components is not None
        and not isinstance(components, list)
    ):
        issues.append(FixIssue(code="root.invalid_components", path="$"))


def _collect_metadata_issues(data: dict, issues: list[FixIssue]) -> None:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return

    timestamp = metadata.get("timestamp")
    if "timestamp" not in metadata or not isinstance(timestamp, str) or timestamp == "":
        issues.append(FixIssue(code="metadata.missing_timestamp", path="$.metadata"))

    component = metadata.get("component")
    if "component" not in metadata or component is None:
        issues.append(FixIssue(code="metadata.missing_component", path="$.metadata"))
        return
    if not isinstance(component, dict):
        issues.append(FixIssue(code="metadata.invalid_component", path="$.metadata"))
        return

    path = "$.metadata.component"
    name = component.get("name")
    component_name = name if _is_non_empty_string(name) else None
    for field_name, code in (
        ("type", "metadata_component.missing_type"),
        ("name", "metadata_component.missing_name"),
        ("version", "metadata_component.missing_version"),
    ):
        if not _is_non_empty_string(component.get(field_name)):
            issues.append(FixIssue(code=code, path=path, component=component_name))

    manufacturer = component.get("manufacturer")
    if (
        not isinstance(manufacturer, dict)
        or not isinstance(manufacturer.get("name"), str)
        or not manufacturer.get("name").strip()
    ):
        issues.append(
            FixIssue(
                code="metadata_component.missing_manufacturer",
                path=path,
                component=component_name,
            )
        )


def _collect_issues(data: dict) -> list[FixIssue]:
    issues: list[FixIssue] = []
    _collect_root_issues(data, issues)
    if isinstance(data.get("metadata"), dict):
        _collect_metadata_issues(data, issues)
    components = data.get("components")
    if isinstance(components, list):
        _collect_component_issues(components, "$.components", issues)
    return issues


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
    filter_external_references = _rule_enabled(
        "components.filter_external_references", options
    )
    filter_properties = _rule_enabled("components.filter_properties", options)
    fill_gost = _rule_enabled("components.fill_missing_gost_properties", options)

    def apply(component: dict) -> None:
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


def _apply_reorder(
    data: dict,
    options: SbomFixOptions,
    counts: dict[str, int],
) -> None:
    if not options.reorder:
        return
    count = int(_reorder_in_place(data, ROOT_PRIORITY))
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        count += int(_reorder_in_place(metadata, METADATA_PRIORITY))
        metadata_component = metadata.get("component")
        if isinstance(metadata_component, dict):
            count += int(
                _reorder_in_place(metadata_component, METADATA_COMPONENT_PRIORITY)
            )
    components = data.get("components")
    if isinstance(components, list):
        count += sum(
            _reorder_component_tree(component)
            for component in components
            if isinstance(component, dict)
        )
    counts["reorder"] = count


def fix_sbom(
    data: dict,
    options: SbomFixOptions,
    now: datetime | None = None,
    remove_fields: Sequence[str] = (),
) -> SbomFixResult:
    if now is None:
        now = datetime.now(timezone.utc)
    fixed_sbom = copy.deepcopy(data)
    counts: dict[str, int] = {}
    removal_counts = remove_optional_fields(
        fixed_sbom, list(remove_fields), options.optional_fields.keep
    )
    _apply_root_rules(fixed_sbom, options, counts)
    _apply_metadata_rules(fixed_sbom, options, counts, now)
    _apply_components_rules(fixed_sbom, options, counts)
    _apply_reorder(fixed_sbom, options, counts)
    stats = [
        FixStat(rule_id=rule_id, count=counts.get(rule_id, 0))
        for rule_id in _enabled_rule_ids(options)
    ]
    stats.extend(
        FixStat(rule_id="optional_fields.remove", count=count, field=path)
        for path, count in removal_counts.items()
    )
    return SbomFixResult(
        changed=any(stat.count > 0 for stat in stats),
        fixed_sbom=fixed_sbom,
        stats=stats,
        issues=_collect_issues(fixed_sbom),
    )
