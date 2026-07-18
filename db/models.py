"""SQLAlchemy ORM models for PetitionsRadar.

Defines the Petition and ScraperRun domain models as SQLAlchemy
declarative classes, plus Python enums for source, status, and topic
fields. These models mirror the schema in db/session.py and can be used
with either SQLite (development) or PostgreSQL (production).
"""

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PetitionSource(str, enum.Enum):
    """Supported petition platforms (German focus)."""

    BUNDESTAG = "bundestag"
    OPENPETITION = "openpetition"
    CHANGE_ORG = "change_org"
    WEACT = "weact"
    PETITIONSPORTAL = "petitionsportal"


class PetitionStatus(str, enum.Enum):
    """Lifecycle status of a petition."""

    OPEN = "open"
    CLOSED = "closed"
    SUCCESSFUL = "successful"
    FAILED = "failed"


class PetitionTopic(str, enum.Enum):
    """Standardized topic categories for petitions."""

    KLIMA = "klima"
    SOZIALES = "soziales"
    BILDUNG = "bildung"
    GESUNDHEIT = "gesundheit"
    VERKEHR = "verkehr"
    DIGITALES = "digitaes"
    INNERES = "inneres"
    WIRTSCHAFT = "wirtschaft"
    UMWELT = "umwelt"
    KULTUR = "kultur"
    DEMOKRATIE = "demokratie"
    SONSTIGES = "sonstiges"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all PetitionsRadar models."""

    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Petition(Base):
    """A petition aggregated from an external platform.

    Attributes:
        id: Internal UUID primary key.
        source: The platform this petition was scraped from.
        external_id: The petition's ID on its source platform.
        title: Human-readable petition title.
        description: Full text description / summary.
        source_url: URL to the official petition page for signing.
        signature_count: Latest scraped signature count.
        signature_goal: Target signature count (nullable if unknown).
        status: Current lifecycle status.
        topic: Standardized topic category.
        created_date: Date the petition was originally created.
        deadline: Closing date (nullable if open-ended).
        image_url: Optional thumbnail image URL.
        first_seen_at: Timestamp when we first discovered this petition.
        last_updated_at: Timestamp of the most recent scrape update.
    """

    __tablename__ = "petitions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    source: Mapped[PetitionSource] = mapped_column(
        Enum(PetitionSource, name="petition_source", native_enum=False),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    signature_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    signature_goal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[PetitionStatus] = mapped_column(
        Enum(PetitionStatus, name="petition_status", native_enum=False),
        default=PetitionStatus.OPEN,
        nullable=False,
    )
    topic: Mapped[Optional[PetitionTopic]] = mapped_column(
        Enum(PetitionTopic, name="petition_topic", native_enum=False),
        nullable=True,
    )
    created_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_petition_source_external"),
        Index("idx_petitions_source", "source"),
        Index("idx_petitions_status", "status"),
        Index("idx_petitions_topic", "topic"),
    )

    def __repr__(self) -> str:
        return (
            f"<Petition id={self.id!r} source={self.source.value} "
            f"title={self.title!r} status={self.status.value}>"
        )


class ScraperRun(Base):
    """Record of a single scraper execution against a source platform.

    Attributes:
        id: Auto-incrementing primary key.
        source: Which platform was scraped.
        started_at: When the scrape began.
        completed_at: When the scrape finished (nullable if still running).
        success: Whether the scrape succeeded (1=success, 0=failure).
        error: Error message if the scrape failed.
        petitions_scraped: Total petitions found in this run.
        petitions_new: Newly discovered petitions.
        petitions_updated: Existing petitions with updated data.
    """

    __tablename__ = "scraper_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[PetitionSource] = mapped_column(
        Enum(PetitionSource, name="petition_source", native_enum=False),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    success: Mapped[Optional[bool]] = mapped_column(
        Integer, nullable=True
    )  # 1=success, 0=failure (stored as INTEGER for sqlite compat)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    petitions_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    petitions_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    petitions_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<ScraperRun id={self.id} source={self.source.value} "
            f"success={self.success} scraped={self.petitions_scraped}>"
        )
