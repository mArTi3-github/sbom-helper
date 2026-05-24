"""Maven Central adapter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from purl2repo.ecosystems.base import EcosystemResolver, Metadata, dedupe_candidates, make_candidate
from purl2repo.http.client import HttpClient
from purl2repo.models import ParsedPurl, RepositoryCandidate
from purl2repo.utils.text import is_docs_like
from purl2repo.utils.urls import is_repo_like_url


class MavenResolver(EcosystemResolver):
    ecosystem = "maven"
    metadata_source = "maven-central-pom"

    def fetch_metadata(self, parsed: ParsedPurl, client: HttpClient) -> Metadata:
        if not parsed.namespace:
            return {}
        version = parsed.version or self._latest_version(parsed, client)
        group_path = parsed.namespace.replace(".", "/")
        url = (
            "https://repo1.maven.org/maven2/"
            f"{group_path}/{parsed.name}/{version}/{parsed.name}-{version}.pom"
        )
        pom = _parse_pom(client.get_text(url))
        metadata: Metadata = {"pom": pom, "effective_version": version}
        if not _scm_has_value(pom):
            parent = pom.get("parent")
            if isinstance(parent, dict):
                parent_poms = self._fetch_parent_chain(parent, client)
                if parent_poms:
                    metadata["parent_poms"] = parent_poms
        return metadata

    def extract_candidates(
        self, parsed: ParsedPurl, metadata: Metadata
    ) -> list[RepositoryCandidate]:
        _ = parsed
        pom = metadata.get("pom")
        if not isinstance(pom, dict):
            pom = {}
        scm = pom.get("scm")
        if not isinstance(scm, dict):
            scm = {}
        candidates: list[RepositoryCandidate | None] = []
        candidates.extend(_scm_candidates(scm, "Maven"))
        parent_poms = metadata.get("parent_poms")
        if isinstance(parent_poms, list):
            for parent_pom in parent_poms:
                if not isinstance(parent_pom, dict):
                    continue
                parent_scm = parent_pom.get("scm")
                if isinstance(parent_scm, dict):
                    candidates.extend(
                        _scm_candidates(parent_scm, "Maven parent", source="pom_parent_scm")
                    )
        elif isinstance(parent_poms, dict):
            parent_pom = parent_poms
            parent_scm = parent_pom.get("scm")
            if isinstance(parent_scm, dict):
                candidates.extend(
                    _scm_candidates(parent_scm, "Maven parent", source="pom_parent_scm")
                )
        homepage = pom.get("url")
        if isinstance(homepage, str) and not is_docs_like(homepage) and is_repo_like_url(homepage):
            candidates.append(
                make_candidate(
                    homepage,
                    "homepage",
                    "Maven project URL points to repo root",
                )
            )
        return dedupe_candidates(candidates)

    def fallback_scrape_pages(self, parsed: ParsedPurl, metadata: Metadata) -> list[str]:
        pages: list[str] = []
        if parsed.namespace:
            pages.append(f"https://central.sonatype.com/artifact/{parsed.namespace}/{parsed.name}")
        pom = metadata.get("pom")
        if isinstance(pom, dict):
            homepage = pom.get("url")
            if isinstance(homepage, str):
                pages.append(homepage)
        return pages

    def _latest_version(self, parsed: ParsedPurl, client: HttpClient) -> str:
        if not parsed.namespace:
            return ""
        group_path = parsed.namespace.replace(".", "/")
        url = f"https://repo1.maven.org/maven2/{group_path}/{parsed.name}/maven-metadata.xml"
        metadata = _parse_maven_metadata(client.get_text(url))
        return metadata.get("release") or metadata.get("latest") or ""

    def _fetch_parent_chain(
        self, parent: dict[str, Any], client: HttpClient, max_depth: int = 4
    ) -> list[Metadata]:
        chain: list[Metadata] = []
        current_parent: dict[str, Any] | None = parent
        for _ in range(max_depth):
            if current_parent is None:
                break
            parent_pom = self._fetch_parent_pom(current_parent, client)
            if parent_pom is None:
                break
            chain.append(parent_pom)
            if _scm_has_value(parent_pom):
                break
            next_parent = parent_pom.get("parent")
            current_parent = next_parent if isinstance(next_parent, dict) else None
        return chain

    def _fetch_parent_pom(self, parent: dict[str, Any], client: HttpClient) -> Metadata | None:
        group_id = parent.get("groupId")
        artifact_id = parent.get("artifactId")
        version = parent.get("version")
        if not isinstance(group_id, str) or not group_id:
            return None
        if not isinstance(artifact_id, str) or not artifact_id:
            return None
        if not isinstance(version, str) or not version:
            return None
        group_path = group_id.replace(".", "/")
        url = (
            "https://repo1.maven.org/maven2/"
            f"{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"
        )
        return _parse_pom(client.get_text(url))


def _parse_pom(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    return {
        "url": _find_text(root, "url"),
        "parent": {
            "groupId": _find_text(root, "parent/groupId"),
            "artifactId": _find_text(root, "parent/artifactId"),
            "version": _find_text(root, "parent/version"),
        },
        "scm": {
            "url": _find_text(root, "scm/url"),
            "connection": _find_text(root, "scm/connection"),
            "developerConnection": _find_text(root, "scm/developerConnection"),
        },
    }


def _parse_maven_metadata(xml_text: str) -> dict[str, str]:
    root = ET.fromstring(xml_text)
    return {
        "latest": _find_text(root, "versioning/latest") or "",
        "release": _find_text(root, "versioning/release") or "",
    }


def _find_text(root: ET.Element, path: str) -> str | None:
    parts = path.split("/")
    current: ET.Element | None = root
    for part in parts:
        if current is None:
            return None
        current = _find_child(current, part)
    if current is None or current.text is None:
        return None
    value = current.text.strip()
    return value or None


def _find_child(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in element:
        if child.tag.rsplit("}", 1)[-1] == local_name:
            return child
    return None


def _scm_has_value(pom: Metadata) -> bool:
    scm = pom.get("scm")
    if not isinstance(scm, dict):
        return False
    return any(isinstance(scm.get(key), str) and scm.get(key) for key in scm)


def _scm_candidates(
    scm: dict[str, Any], label: str, *, source: str = "pom_scm"
) -> list[RepositoryCandidate | None]:
    candidates: list[RepositoryCandidate | None] = []
    for key in ("url", "connection", "developerConnection"):
        value = scm.get(key)
        if isinstance(value, str):
            candidates.append(make_candidate(value, source, f"Candidate from {label} scm.{key}"))
    return candidates
