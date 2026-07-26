from __future__ import annotations

import logging

from ..purl_utils import PurlValidationError, validate
from .interface import Resolution, Resolver

logger = logging.getLogger(__name__)


class ApkResolver(Resolver):

    @property
    def name(self) -> str:
        return "apk"

    async def resolve(self, purl: str) -> Resolution:
        try:
            components = validate(purl)
        except PurlValidationError as e:
            return Resolution(purl=purl, warnings=[f"Invalid PURL: {e}"])

        if components.type != "apk":
            return Resolution(
                purl=purl,
                warnings=[f"Unsupported package type '{components.type}' for APK resolver"],
            )

        return Resolution(
            purl=purl,
            repository_url="https://github.com/alpinelinux/aports/",
        )
