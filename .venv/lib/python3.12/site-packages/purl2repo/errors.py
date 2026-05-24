"""Explicit purl2repo error hierarchy."""


class Purl2RepoError(Exception):
    """Base class for all package-specific failures."""


class InvalidPurlError(Purl2RepoError):
    """Raised when a package URL is malformed."""


class UnsupportedEcosystemError(Purl2RepoError):
    """Raised when no resolver exists for a PURL type."""


class MetadataFetchError(Purl2RepoError):
    """Raised when registry metadata cannot be fetched or parsed."""


class ResolutionError(Purl2RepoError):
    """Raised when resolution cannot complete."""


class NoRepositoryFoundError(ResolutionError):
    """Raised in strict mode when no suitable repository was found."""


class NoReleaseFoundError(ResolutionError):
    """Raised in strict release mode when no version link was found."""
