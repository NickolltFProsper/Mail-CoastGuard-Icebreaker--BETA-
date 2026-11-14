"""Pydantic data models for Mail CoastGuard.

Strict validation, forbidden extra fields, and anti-abuse length limits.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmailInput(BaseModel):
    """Input email payload to be analyzed."""

    model_config = ConfigDict(extra="forbid", strict=True)

    sender: str = Field(..., max_length=320, description="Sender email address")
    display_name: str = Field("", max_length=200, description="Sender display name")
    reply_to: str = Field("", max_length=320, description="Reply-To address")
    subject: str = Field("", max_length=500, description="Subject line")
    body: str = Field("", max_length=50_000, description="Plain text email body")
    attachments: list[str] = Field(default_factory=list, max_length=50, description="List of attachment filenames")

    @field_validator("attachments")
    @classmethod
    def validate_attachment_names(cls, v: list[str]) -> list[str]:
        for name in v:
            if not isinstance(name, str):
                raise ValueError("Attachment items must be strings")
            if len(name) > 255:
                raise ValueError("Attachment filename exceeds 255 characters")
        return v


class LayerResult(BaseModel):
    """Result from an individual analysis layer."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="layer1, layer2, or layer3")
    level: Literal["GREEN", "YELLOW", "RED", "BLACK"] = Field(..., description="Severity level")
    reasons: list[str] = Field(default_factory=list, description="Descriptive reasons in Spanish")
    score: int | None = Field(default=None, description="Score calculated in Layer 2")


class AIResult(BaseModel):
    """Validated structured output from Layer 3 (AI analysis)."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["phishing", "suspicious", "no_indicators"]
    level: Literal["RED", "YELLOW", "GREEN"]
    reasons: list[str] = Field(default_factory=list, max_length=5)
    confidence: float = Field(..., ge=0.0, le=1.0)


class AnalyzeResponse(BaseModel):
    """Response schema for POST /analyze (Layers 1 and 2)."""

    model_config = ConfigDict(extra="forbid")

    final_level: Literal["GREEN", "YELLOW", "RED", "BLACK"]
    message: str
    layers: list[LayerResult]


class DeepAnalysisResponse(BaseModel):
    """Response schema for POST /deep-analysis (Layers 1, 2, and 3)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "unavailable"]
    notice: str | None = None
    final_level: Literal["GREEN", "YELLOW", "RED", "BLACK"]
    message: str
    layers: list[LayerResult]
    layer3: AIResult | None = None


# Admin API schemas
class AdminListUpdateRequest(BaseModel):
    """Payload for PUT /api/admin/v1/lists/{list_name}."""

    model_config = ConfigDict(extra="forbid")
    data: Any
