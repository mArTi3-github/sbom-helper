from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

SPEC_VERSION_PATTERN = re.compile(r"^\d+\.\d+$")
ALLOWED_SPEC_VERSIONS = {"1.6", "1.7"}

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


def fix_sbom(
    data: dict,
    options: SbomFixOptions,
    now: datetime | None = None,
) -> SbomFixResult:
    fixed_sbom = copy.deepcopy(data)
    stats = [FixStat(rule_id=rule_id, count=0) for rule_id in _enabled_rule_ids(options)]
    return SbomFixResult(
        changed=False,
        fixed_sbom=fixed_sbom,
        stats=stats,
        issues=[],
    )
