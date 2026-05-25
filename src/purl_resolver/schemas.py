from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class ResolveRequest(BaseModel):
    purl: str = Field(..., min_length=1, description="Package URL to resolve")


class ResolveResponse(BaseModel):
    purl: str
    repository_url: str | None = None
    repository_type: str | None = None
    repository_kind: str | None = None
    confidence: str | None = None
    evidence: list[str] = []
    warnings: list[str] = []
    version_reference: str | None = None


class ErrorResponse(BaseModel):
    error: str
    message: str


@dataclass(frozen=True)
class ResolveResult:
    response: ResolveResponse | None = None
    error_status: int | None = None
    error_body: dict[str, str] | None = None

    @staticmethod
    def ok(response: ResolveResponse) -> ResolveResult:
        return ResolveResult(response=response)

    @staticmethod
    def err(status: int, error: str, message: str) -> ResolveResult:
        return ResolveResult(
            error_status=status,
            error_body={"error": error, "message": message},
        )
