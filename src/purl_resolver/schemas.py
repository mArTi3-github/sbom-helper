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