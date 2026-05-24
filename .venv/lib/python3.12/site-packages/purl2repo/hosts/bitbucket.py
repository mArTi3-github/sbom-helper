"""Bitbucket host adapter."""

from purl2repo.hosts.base import HostAdapter, ordered_version_variants
from purl2repo.models import ReleaseLink
from purl2repo.utils.urls import normalize_repo_url
from purl2repo.utils.versions import is_commit_like, preferred_v_tag


class BitbucketAdapter(HostAdapter):
    host_name = "bitbucket.org"

    def normalize_repo_url(self, url: str) -> str | None:
        return normalize_repo_url(url)

    def infer_release_link(self, repo_url: str, version: str) -> ReleaseLink | None:
        candidates = self.candidate_release_links(repo_url, version)
        if is_commit_like(version):
            return next((candidate for candidate in candidates if candidate.kind == "commit"), None)
        preferred = f"/{preferred_v_tag(version)}"
        return next(
            (candidate for candidate in candidates if candidate.url.endswith(preferred)),
            None,
        )

    def candidate_release_links(self, repo_url: str, version: str) -> list[ReleaseLink]:
        normalized = self.normalize_repo_url(repo_url)
        if not normalized:
            return []
        links: list[ReleaseLink] = []
        if is_commit_like(version):
            links.append(
                ReleaseLink(
                    url=f"{normalized}/commits/{version}",
                    kind="commit",
                    version=version,
                    source="bitbucket",
                )
            )
        links.extend(
            ReleaseLink(
                url=f"{normalized}/src/{tag}",
                kind="source",
                version=version,
                source="bitbucket",
            )
            for tag in ordered_version_variants(version)
        )
        return links
