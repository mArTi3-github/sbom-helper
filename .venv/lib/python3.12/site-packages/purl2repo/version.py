"""Package version metadata."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("purl2repo")
except PackageNotFoundError:
    __version__ = "0+unknown"
