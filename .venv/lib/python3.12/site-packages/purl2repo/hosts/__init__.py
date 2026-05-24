"""Host adapters."""

from .bitbucket import BitbucketAdapter
from .generic_git import GenericGitAdapter
from .github import GitHubAdapter
from .gitlab import GitLabAdapter

__all__ = ["BitbucketAdapter", "GenericGitAdapter", "GitHubAdapter", "GitLabAdapter"]
