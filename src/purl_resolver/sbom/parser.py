from __future__ import annotations


class SbomParseError(ValueError):
    ...


class CycloneDXParser:

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
        return data
