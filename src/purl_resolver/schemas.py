from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class ResolveRequest(BaseModel):
    purl: str = Field(..., min_length=1, description="Package URL to resolve")


class ResolveResponse(BaseModel):
    purl: str
    repository_url: str | None = None
    warnings: list[str] = []
    resolver: str = ""
    found_by: str = ""
    resolved_at: str = ""



@dataclass(frozen=True)
class ResolveResult:
    response: ResolveResponse | None = None
    error_status: int | None = None
    error_body: dict[str, str] | None = None

    @staticmethod
    def ok(response: ResolveResponse) -> ResolveResult:
        return ResolveResult(response=response)

    @staticmethod
    def err(status_code: int, error: str, detail: str | None = None) -> ResolveResult:
        return ResolveResult(
            error_status=status_code,
            error_body={"error": error} if detail is None else {"error": error, "detail": detail},
        )


class ImportStrategy(str, Enum):
    upsert = "upsert"
    skip_existing = "skip_existing"


class PurlListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)
    search: str | None = None
    resolver: str | None = None
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


class PurlCreateRequest(BaseModel):
    purl: str = Field(..., min_length=1)
    repository_url: str = Field(..., min_length=1)


class PurlDeleteRequest(BaseModel):
    purls: list[str]


class ExportRequest(BaseModel):
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
