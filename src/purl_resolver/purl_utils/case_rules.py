from __future__ import annotations

from typing import Literal

from packageurl import PackageURL, quote, unquote
from packageurl.validate import DEFINITIONS_BY_TYPE

PurlCaseMode = Literal["sbom_checker", "purl_spec"]

PURL_SPEC_LOWERCASE_NAMESPACE = frozenset({
    "alpm",
    "apk",
    "bitbucket",
    "brew",
    "composer",
    "deb",
    "github",
    "hex",
    "luarocks",
    "qpkg",
    "rpm",
    "vscode-extension",
    "yocto",
})

PURL_SPEC_LOWERCASE_NAME = frozenset({
    "alpm",
    "apk",
    "bitbucket",
    "bitnami",
    "brew",
    "chrome-extension",
    "composer",
    "deb",
    "github",
    "hex",
    "luarocks",
    "oci",
    "otp",
    "pub",
    "pypi",
    "vscode-extension",
})

PURL_SPEC_LOWERCASE_VERSION = frozenset({
    "huggingface",
    "oci",
    "pypi",
    "vscode-extension",
})

_CHECKER_EXTRA_TYPE_FLAGS: dict[str, tuple[bool, bool, bool]] = {
    "bazel": (False, False, True),
    "brew": (False, False, True),
    "chrome-extension": (False, False, True),
    "git": (True, True, True),
    "julia": (False, True, True),
    "opam": (False, True, True),
    "otp": (False, False, True),
    "vcpkg": (False, False, True),
    "vscode-extension": (False, False, False),
    "yocto": (False, True, True),
}


def _checker_type_flags() -> dict[str, tuple[bool, bool, bool]]:
    flags = {
        purl_type: (
            definition.namespace_case_sensitive,
            definition.name_case_sensitive,
            definition.version_case_sensitive,
        )
        for purl_type, definition in DEFINITIONS_BY_TYPE.items()
    }
    flags.update(_CHECKER_EXTRA_TYPE_FLAGS)
    return flags


_CHECKER_TYPE_FLAGS = _checker_type_flags()


def _case_targets(
    purl_type: str, mode: PurlCaseMode
) -> tuple[bool, bool, bool]:
    if mode == "purl_spec":
        return (
            purl_type in PURL_SPEC_LOWERCASE_NAMESPACE,
            purl_type in PURL_SPEC_LOWERCASE_NAME,
            purl_type in PURL_SPEC_LOWERCASE_VERSION,
        )

    flags = _CHECKER_TYPE_FLAGS.get(purl_type)
    if flags is None:
        return False, False, False
    namespace_case_sensitive, name_case_sensitive, version_case_sensitive = flags
    if purl_type == "cpan":
        namespace_case_sensitive = True
    return (
        not namespace_case_sensitive,
        not name_case_sensitive,
        not version_case_sensitive,
    )


def _has_upper(value: str | None) -> bool:
    if not value:
        return False
    decoded = unquote(value)
    return decoded != decoded.lower()


def _lower(value: str) -> str:
    return quote(unquote(value).lower())


def _lower_namespace(namespace: str) -> str:
    return "/".join(_lower(segment) for segment in namespace.split("/"))


def _suffix(purl: str) -> str:
    query = purl.find("?")
    fragment = purl.find("#")
    if query != -1 and (fragment == -1 or query < fragment):
        return purl[query:]
    if fragment != -1:
        return purl[fragment:]
    return ""


def lowercase_purl(purl: str, mode: PurlCaseMode) -> str | None:
    try:
        raw = PackageURL.from_string(purl, normalize_purl=False)
    except ValueError:
        return None

    lower_namespace, lower_name, lower_version = _case_targets(raw.type, mode)

    namespace = raw.namespace or None
    new_namespace = namespace
    if namespace and lower_namespace:
        segments = namespace.split("/")
        if any(_has_upper(segment) for segment in segments):
            new_namespace = _lower_namespace(namespace)

    new_name = raw.name
    if lower_name and _has_upper(raw.name):
        new_name = _lower(raw.name)

    new_version = raw.version
    if new_version and lower_version and _has_upper(new_version):
        new_version = _lower(new_version)

    if (
        new_namespace == namespace
        and new_name == raw.name
        and new_version == raw.version
    ):
        return None

    rebuilt = f"pkg:{raw.type}/"
    if new_namespace:
        rebuilt += f"{new_namespace}/"
    rebuilt += new_name
    if new_version:
        rebuilt += f"@{new_version}"
    rebuilt += _suffix(purl)
    return rebuilt
