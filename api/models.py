"""Pydantic models for petition data.

Defines schemas for petition metadata aggregation from multiple German
petition platforms (Bundestag, openPetition, Change.org, WeAct, petitionsportal).
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


class PetitionSource(str, Enum):
    """Supported petition platforms."""

    BUNDESTAG = "bundestag"
    OPENPETITION = "openpetition"
    CHANGE_ORG = "change_org"
    WEACT = "weact"
    PETITIONSPORTAL = "petitionsportal"


class PetitionTopic(str, Enum):
    """Standardized petition topic categories."""

    KLIMA = "klima"
    SOZIALES = "soziales"
    BILDUNG = "bildung"
    GESUNDHEIT = "gesundheit"
    DIGITALES = "digitales"
    VERKEHR = "verkehr"
    WOHNEN = "wohnen"
    ARBEIT = "arbeit"
    INNERES = "inneres"
    AUSSEN = "aussen"
    UMWELT = "umwelt"
    VERBRAUCHERSCHUTZ = "verbraucherschutz"
    SONSTIGES = "sonstiges"


class PetitionStatus(str, Enum):
    """Lifecycle status of a petition."""

    OPEN = "open"
    CLOSED = "closed"
    SUCCESSFUL = "successful"
    FAILED = "failed"


class PetitionBase(BaseModel):
    """Core petition fields shared across input/output schemas."""

    source: PetitionSource = Field(..., description="Platform where petition originates")
    source_url: str = Field(..., description="Official URL for signing the petition")
    external_id: str = Field(..., description="ID on the source platform")
    title: str = Field(..., min_length=1, max_length=500, description="Petition title")
    description: str = Field("", description="Full petition description text")
    topic: PetitionTopic = Field(
        PetitionTopic.SONSTIGES,
        description="Standardized topic category",
    )
    signature_count: int = Field(0, ge=0, description="Latest scraped signature count")
    signature_goal: Optional[int] = Field(None, ge=0, description="Target signature count if known")
    status: PetitionStatus = Field(PetitionStatus.OPEN, description="Current petition status")
    created_date: Optional[date] = Field(None, description="Date petition was created on source platform")
    deadline: Optional[date] = Field(None, description="Closing date if applicable")
    image_url: Optional[str] = Field(None, description="URL of thumbnail image for card display")


class PetitionCreate(PetitionBase):
    """Schema for creating a new petition record (e.g., from scraper output)."""

    id: UUID = Field(default_factory=uuid4, description="Internal unique identifier")
    last_scraped: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of most recent successful scrape",
    )

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, v: str) -> str:
        """Ensure source_url is a valid absolute URL."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return v

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: Optional[str]) -> Optional[str]:
        """Ensure image_url is a valid absolute URL when provided."""
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("image_url must be an absolute HTTP(S) URL")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "source": "bundestag",
                    "source_url": "https://epetitionen.bundestag.de/petitionen/_action.html?petitionId=12345",
                    "external_id": "12345",
                    "title": "Tempolimit 130 km/h auf Autobahnen",
                    "description": "Wir fordern ein allgemeines Tempolimit...",
                    "topic": "klima",
                    "signature_count": 25000,
                    "signature_goal": 50000,
                    "status": "open",
                    "created_date": "2026-01-15",
                    "deadline": "2026-07-30",
                    "image_url": None,
                    "last_scraped": "2026-07-16T12:00:00",
                }
            ]
        }
    }


class PetitionUpdate(BaseModel):
    """Schema for partial updates to an existing petition (e.g., after re-scrape)."""

    signature_count: Optional[int] = Field(None, ge=0, description="Updated signature count")
    signature_goal: Optional[int] = Field(None, ge=0, description="Updated target signature count")
    status: Optional[PetitionStatus] = Field(None, description="Updated status")
    deadline: Optional[date] = Field(None, description="Updated closing date")
    description: Optional[str] = Field(None, description="Updated description text")
    image_url: Optional[str] = Field(None, description="Updated thumbnail URL")
    last_scraped: Optional[datetime] = Field(None, description="Timestamp of this scrape")

    model_config = {"extra": "forbid"}


class PetitionResponse(PetitionBase):
    """Schema returned by API endpoints for a single petition."""

    id: UUID = Field(..., description="Internal unique identifier")
    last_scraped: datetime = Field(..., description="When this record was last refreshed from source")
    created_at: datetime = Field(..., description="When this record was first stored")
    updated_at: datetime = Field(..., description="When this record was last modified")

    model_config = {"from_attributes": True}


class PetitionListResponse(BaseModel):
    """Envelope for paginated petition list endpoints."""

    data: list[PetitionResponse] = Field(default_factory=list, description="Petition records for this page")
    meta: dict = Field(
        default_factory=dict,
        description="Pagination metadata: total, page, page_size",
    )

    @field_validator("meta")
    @classmethod
    def validate_meta(cls, v: dict) -> dict:
        """Ensure meta contains required pagination keys."""
        required = {"total", "page", "page_size"}
        missing = required - v.keys()
        if missing:
            raise ValueError(f"meta missing required keys: {missing}")
        return v


class PetitionFilter(BaseModel):
    """Query parameters for filtering petition listings."""

    topic: Optional[PetitionTopic] = Field(None, description="Filter by standardized topic")
    source: Optional[PetitionSource] = Field(None, description="Filter by petition platform")
    status: Optional[PetitionStatus] = Field(None, description="Filter by petition status")
    search: Optional[str] = Field(None, max_length=200, description="Keyword search in title/description")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=50, description="Items per page (max 50)")
