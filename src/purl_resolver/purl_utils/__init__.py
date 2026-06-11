from __future__ import annotations

from dataclasses import dataclass, field

from packageurl import PackageURL


class PurlValidationError(Exception):
    ...


@dataclass(frozen=True)
class PurlComponents:
    scheme: str = "pkg"
    type: str = ""
    namespace: str | None = None
    name: str = ""
    version: str | None = None
    qualifiers: dict[str, str] | None = None
    subpath: str | None = None


def validate(purl: str) -> PurlComponents:
    try:
        parsed = PackageURL.from_string(purl)
    except ValueError as e:
        raise PurlValidationError(str(e)) from e
    return PurlComponents(
        scheme="pkg",
        type=parsed.type,
        namespace=parsed.namespace,
        name=parsed.name,
        version=parsed.version,
        qualifiers=parsed.qualifiers,
        subpath=parsed.subpath,
    )


def normalize(components: PurlComponents) -> str:
    purl_obj = PackageURL(
        type=components.type,
        namespace=components.namespace,
        name=components.name,
    )
    return purl_obj.to_string()


def safe_normalize(purl: str) -> str:
    try:
        return normalize(validate(purl))
    except Exception:
        return purl