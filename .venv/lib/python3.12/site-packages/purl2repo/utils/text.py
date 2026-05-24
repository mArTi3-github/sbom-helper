"""Small text classification helpers used by scoring and adapters."""

SOURCE_LABELS = {
    "code",
    "repo",
    "repository",
    "scm",
    "source",
    "source code",
    "sourcecode",
    "sources",
}

DOCS_WORDS = {"doc", "docs", "documentation", "readthedocs", "docs.rs", "pages"}
ISSUE_WORDS = {"bug", "bugs", "issue", "issues", "tracker"}


def normalize_label(label: str) -> str:
    return " ".join(label.replace("_", " ").replace("-", " ").lower().split())


def is_source_label(label: str) -> bool:
    normalized = normalize_label(label)
    return normalized in SOURCE_LABELS or any(word in normalized.split() for word in SOURCE_LABELS)


def is_docs_like(value: str) -> bool:
    lowered = value.lower()
    return any(word in lowered for word in DOCS_WORDS)


def is_issue_like(value: str) -> bool:
    lowered = value.lower()
    return any(f"/{word}" in lowered or word in lowered.split() for word in ISSUE_WORDS)


def package_name_tokens(name: str) -> set[str]:
    return {token for token in name.lower().replace("_", "-").split("-") if token}
