"""Consistent evidence and warning message helpers."""


def fetched(source: str) -> str:
    return f"Fetched package metadata from {source}"


def selected_candidate() -> str:
    return "Selected highest scoring repository candidate"


def skipped_release_no_version() -> str:
    return "Version not supplied; skipped version-specific release resolution"


def resolved_release() -> str:
    return "Resolved version-specific release link"


def verified_release() -> str:
    return "Verified version-specific release link exists"


def used_fallback_scraping() -> str:
    return (
        "Used fallback scraping because structured metadata did not yield "
        "a usable repository candidate"
    )


def no_repository_warning() -> str:
    return "No suitable repository candidate was found"


def weak_candidate_warning() -> str:
    return "Only weak candidates were found"


def no_release_warning() -> str:
    return "Repository resolved, but no version-specific release link could be inferred"


def unverified_release_warning() -> str:
    return "Inferred release link could not be verified"


def ambiguous_warning() -> str:
    return "Multiple plausible repositories found with similar scores"
