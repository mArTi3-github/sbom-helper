from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

REPOSITORY_KINDS: frozenset[str] = frozenset({"vcs", "source-distribution"})


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
    resolver: str = ""
    resolved_at: str = ""


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


class ImportStrategy(str, Enum):
    upsert = "upsert"
    skip_existing = "skip_existing"


class PurlListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)
    search: str | None = None
    resolver: str | None = None
    confidence: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort_by: str = "resolved_at"
    sort_order: str = "desc"


class PurlListResponse(BaseModel):
    rows: list[ResolveResponse]
    total: int
    page: int
    page_size: int


class PurlUpdateRequest(BaseModel):
    purl: str | None = None
    repository_url: str | None = None


class PurlDeleteRequest(BaseModel):
    purls: list[str]


class DeleteResponse(BaseModel):
    deleted: int


class ImportErrorItem(BaseModel):
    row: int
    error: str


class ImportResponse(BaseModel):
    imported: int
    skipped: int = 0
    errors: list[ImportErrorItem] = []
