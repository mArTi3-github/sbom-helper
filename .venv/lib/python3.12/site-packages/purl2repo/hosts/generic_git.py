"""Generic git host adapter."""

from purl2repo.hosts.base import HostAdapter
from purl2repo.models import ReleaseLink
from purl2repo.utils.urls import normalize_repo_url


class GenericGitAdapter(HostAdapter):
    host_name = "generic"

    def normalize_repo_url(self, url: str) -> str | None:
        return normalize_repo_url(url)

    def infer_release_link(self, repo_url: str, version: str) -> ReleaseLink | None:
        _ = repo_url, version
        return None
