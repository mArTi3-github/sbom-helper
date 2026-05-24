"""Host adapter abstraction."""

from abc import ABC, abstractmethod

from purl2repo.models import ReleaseLink
from purl2repo.utils.versions import version_variants


class HostAdapter(ABC):
    host_name: str

    @abstractmethod
    def normalize_repo_url(self, url: str) -> str | None:
        """Normalize a repository URL for this host."""

    @abstractmethod
    def infer_release_link(self, repo_url: str, version: str) -> ReleaseLink | None:
        """Infer a version-specific release or source URL."""

    def candidate_release_links(self, repo_url: str, version: str) -> list[ReleaseLink]:
        """Return release links in preferred order for optional verification."""

        link = self.infer_release_link(repo_url, version)
        return [link] if link else []


def ordered_version_variants(version: str) -> list[str]:
    return version_variants(version)
