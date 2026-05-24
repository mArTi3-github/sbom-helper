"""PURL normalization."""

from purl2repo.purl.parse import parse_purl, purl_to_string


def normalize_purl(purl: str) -> str:
    """Return a canonical Package URL string."""

    return purl_to_string(parse_purl(purl))
