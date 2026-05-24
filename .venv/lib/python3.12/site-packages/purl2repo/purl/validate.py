"""PURL validation."""

from purl2repo.models import ParsedPurl
from purl2repo.purl.parse import parse_purl


def validate_purl(purl: str) -> ParsedPurl:
    """Validate and return a parsed PURL."""

    return parse_purl(purl)
