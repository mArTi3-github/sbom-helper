"""Package URL parser.

The parser intentionally implements the subset of the Package URL grammar that
matters for resolution while preserving qualifiers and subpaths for callers.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote

from purl2repo.errors import InvalidPurlError
from purl2repo.models import ParsedPurl

_TYPE_RE = re.compile(r"^[A-Za-z0-9.+-]+$")
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_HEX_VERSION_RE = re.compile(r"^[0-9A-Fa-f]+$")
_PYPI_NAME_RE = re.compile(r"[-_.]+")


def _decode_component(value: str, label: str) -> str:
    if _BAD_PERCENT_RE.search(value):
        raise InvalidPurlError(f"Malformed percent-encoding in {label}.")
    decoded = unquote(value)
    if decoded == "":
        raise InvalidPurlError(f"Empty {label} is not allowed.")
    return decoded


def _parse_qualifiers(query: str | None) -> dict[str, str]:
    if query is None:
        return {}
    if query == "":
        raise InvalidPurlError("Qualifier separator '?' must be followed by key=value pairs.")

    qualifiers: dict[str, str] = {}
    for item in query.split("&"):
        if not item or "=" not in item:
            raise InvalidPurlError("Qualifiers must use key=value syntax.")
        key, value = item.split("=", 1)
        decoded_key = _decode_component(key, "qualifier key").lower()
        decoded_value = _decode_component(value, f"qualifier value for {decoded_key}")
        if decoded_key in qualifiers:
            raise InvalidPurlError(f"Duplicate qualifier key: {decoded_key}")
        qualifiers[decoded_key] = decoded_value
    return qualifiers


def _encode_path_component(value: str) -> str:
    return quote(value, safe=".-_~")


def _encode_qualifier_component(value: str) -> str:
    return quote(value, safe=".-_~:")


def _decode_subpath(value: str) -> str:
    subpath = _decode_component(value, "subpath").strip("/")
    if not subpath:
        raise InvalidPurlError("Empty subpath is not allowed.")
    return subpath


def _split_package_and_version(remainder: str) -> tuple[str, str | None]:
    version_index = remainder.rfind("@")
    last_slash_index = remainder.rfind("/")
    if version_index <= last_slash_index:
        return remainder, None

    package_path = remainder[:version_index]
    version = remainder[version_index + 1 :]
    final_package_segment = package_path[package_path.rfind("/") + 1 :]
    if "@" in final_package_segment:
        raise InvalidPurlError("PURL contains multiple version separators.")
    return package_path, version


def _normalize_package_parts(
    purl_type: str,
    namespace: str | None,
    name: str,
    version: str | None,
    qualifiers: dict[str, str],
) -> tuple[str | None, str, str | None]:
    if purl_type == "pypi":
        name = _PYPI_NAME_RE.sub("-", name).lower()
    elif purl_type in {"github", "bitbucket"}:
        namespace = namespace.lower() if namespace else None
        name = name.lower()
    elif purl_type == "mlflow":
        repository_url = qualifiers.get("repository_url", "")
        if "azuredatabricks.net" in repository_url.lower():
            namespace = namespace.lower() if namespace else None
            name = name.lower()
    elif purl_type == "huggingface" and version and _HEX_VERSION_RE.fullmatch(version):
        version = version.lower()
    return namespace, name, version


def parse_purl(purl: str) -> ParsedPurl:
    """Parse and validate a Package URL string."""

    if not isinstance(purl, str) or not purl.strip():
        raise InvalidPurlError("PURL must be a non-empty string.")
    raw = purl.strip()
    if not raw.startswith("pkg:"):
        raise InvalidPurlError("PURL must start with 'pkg:'.")

    without_scheme = raw[4:].lstrip("/")

    main_and_query, sep, subpath_raw = without_scheme.partition("#")
    subpath = _decode_subpath(subpath_raw) if sep else None

    path_part, query_sep, query = main_and_query.partition("?")
    qualifiers = _parse_qualifiers(query if query_sep else None)

    type_part, slash, remainder = path_part.partition("/")
    if not slash:
        raise InvalidPurlError("PURL must include a type and package name separated by '/'.")
    if not type_part or not _TYPE_RE.match(type_part):
        raise InvalidPurlError("PURL type is missing or invalid.")

    package_path, version_raw = _split_package_and_version(remainder)
    version = _decode_component(version_raw, "version") if version_raw is not None else None

    if package_path == "" or package_path.endswith("/") or package_path.startswith("/"):
        raise InvalidPurlError("PURL package path is malformed.")
    parts = [_decode_component(part, "package path component") for part in package_path.split("/")]
    if len(parts) == 1:
        namespace = None
        name = parts[0]
    else:
        namespace = "/".join(parts[:-1])
        name = parts[-1]

    namespace, name, version = _normalize_package_parts(
        type_part.lower(), namespace, name, version, qualifiers
    )

    parsed = ParsedPurl(
        raw=raw,
        type=type_part.lower(),
        namespace=namespace,
        name=name,
        version=version,
        qualifiers=dict(sorted(qualifiers.items())),
        subpath=subpath,
    )
    return parsed


def purl_to_string(parsed: ParsedPurl) -> str:
    """Return a canonical string representation for a parsed PURL."""

    path_parts: list[str] = []
    if parsed.namespace:
        path_parts.extend(_encode_path_component(part) for part in parsed.namespace.split("/"))
    path_parts.append(_encode_path_component(parsed.name))
    value = f"pkg:{parsed.type}/{'/'.join(path_parts)}"
    if parsed.version:
        value = f"{value}@{_encode_path_component(parsed.version)}"
    if parsed.qualifiers:
        query = "&".join(
            f"{_encode_qualifier_component(key)}={_encode_qualifier_component(value)}"
            for key, value in sorted(parsed.qualifiers.items())
        )
        value = f"{value}?{query}"
    if parsed.subpath:
        value = f"{value}#{'/'.join(_encode_path_component(p) for p in parsed.subpath.split('/'))}"
    return value
