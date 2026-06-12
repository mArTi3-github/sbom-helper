from __future__ import annotations


class SbomParseError(ValueError):
    ...


class CycloneDXParser:
    SUPPORTED_VERSIONS = {"1.6"}

    @classmethod
    def parse(cls, data: object) -> dict:
        if not isinstance(data, dict):
            raise SbomParseError("Root element must be a JSON object")
        bom_format = data.get("bomFormat")
        if not bom_format:
            raise SbomParseError("Missing required field: bomFormat")
        if bom_format != "CycloneDX":
            raise SbomParseError(
                f"Unsupported bomFormat: {bom_format}. Expected: CycloneDX"
            )
        spec_version = data.get("specVersion")
        if not spec_version:
            raise SbomParseError("Missing required field: specVersion")
        if spec_version not in cls.SUPPORTED_VERSIONS:
            raise SbomParseError(
                f"Unsupported specVersion: {spec_version}. "
                f"Supported: {', '.join(sorted(cls.SUPPORTED_VERSIONS))}"
            )
        return data
