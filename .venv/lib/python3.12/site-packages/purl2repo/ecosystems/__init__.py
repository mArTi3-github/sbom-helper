"""Supported ecosystem adapters."""

from .cargo import CargoResolver
from .golang import GoResolver
from .maven import MavenResolver
from .npm import NpmResolver
from .nuget import NuGetResolver
from .pypi import PyPiResolver

__all__ = [
    "CargoResolver",
    "GoResolver",
    "MavenResolver",
    "NpmResolver",
    "NuGetResolver",
    "PyPiResolver",
]
