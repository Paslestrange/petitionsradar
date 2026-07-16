"""Tests for api.models Pydantic schemas."""

from datetime import date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.models import (
    PetitionCreate,
    PetitionFilter,
    PetitionListResponse,
    PetitionResponse,
    PetitionSource,
    PetitionStatus,
    PetitionTopic,
    PetitionUpdate,
)


# ── PetitionCreate ──────────────────────────────────────────────────────────


def _valid_create_kwargs(**overrides):
    base = dict(
        source=PetitionSource.BUNDESTAG,
        source_url="https://epetitionen.bundestag.de/petition/12345",
        external_id="12345",
        title="Tempolimit 130 km/h",
        topic=PetitionTopic.KLIMA,
    )
    base.update(overrides)
    return base


def test_create_defaults():
    p = PetitionCreate(**_valid_create_kwargs())
    assert p.status == PetitionStatus.OPEN
    assert p.signature_count == 0
    assert p.signature_goal is None
    assert p.topic == PetitionTopic.KLIMA
    assert isinstance(p.id, type(uuid4()))
    assert isinstance(p.last_scraped, datetime)


def test_create_explicit_fields():
    p = PetitionCreate(
        **_valid_create_kwargs(
            signature_count=25000,
            signature_goal=50000,
            status=PetitionStatus.OPEN,
            created_date=date(2026, 1, 15),
            deadline=date(2026, 7, 30),
        )
    )
    assert p.signature_count == 25000
    assert p.signature_goal == 50000
    assert p.deadline == date(2026, 7, 30)


def test_create_rejects_negative_signatures():
    with pytest.raises(ValidationError, match="greater_than_equal"):
        PetitionCreate(**_valid_create_kwargs(signature_count=-1))


def test_create_rejects_bad_source_url():
    with pytest.raises(ValidationError, match="source_url"):
        PetitionCreate(**_valid_create_kwargs(source_url="not-a-url"))


def test_create_rejects_bad_image_url():
    with pytest.raises(ValidationError, match="image_url"):
        PetitionCreate(**_valid_create_kwargs(image_url="ftp://bad"))


def test_create_rejects_empty_title():
    with pytest.raises(ValidationError):
        PetitionCreate(**_valid_create_kwargs(title=""))


def test_create_rejects_title_too_long():
    with pytest.raises(ValidationError):
        PetitionCreate(**_valid_create_kwargs(title="x" * 501))


def test_create_rejects_negative_signature_goal():
    with pytest.raises(ValidationError):
        PetitionCreate(**_valid_create_kwargs(signature_goal=-10))


def test_create_accepts_all_sources():
    for src in PetitionSource:
        p = PetitionCreate(**_valid_create_kwargs(source=src))
        assert p.source == src


def test_create_accepts_all_topics():
    for topic in PetitionTopic:
        p = PetitionCreate(**_valid_create_kwargs(topic=topic))
        assert p.topic == topic


# ── PetitionUpdate ──────────────────────────────────────────────────────────


def test_update_all_optional():
    u = PetitionUpdate()
    assert u.signature_count is None
    assert u.status is None


def test_update_partial():
    u = PetitionUpdate(signature_count=30000, status=PetitionStatus.CLOSED)
    assert u.signature_count == 30000
    assert u.status == PetitionStatus.CLOSED


def test_update_forbids_extra_fields():
    with pytest.raises(ValidationError):
        PetitionUpdate(signature_count=100, bogus="nope")


def test_update_rejects_negative_count():
    with pytest.raises(ValidationError):
        PetitionUpdate(signature_count=-5)


# ── PetitionResponse ────────────────────────────────────────────────────────


def test_response_from_attributes():
    now = datetime.utcnow()
    p = PetitionCreate(**_valid_create_kwargs())
    r = PetitionResponse.model_validate(
        {
            **p.model_dump(),
            "created_at": now,
            "updated_at": now,
        }
    )
    assert r.id == p.id
    assert r.created_at == now


# ── PetitionListResponse ────────────────────────────────────────────────────


def test_list_response_valid_meta():
    now = datetime.utcnow()
    p = PetitionCreate(**_valid_create_kwargs())
    r = PetitionResponse.model_validate({**p.model_dump(), "created_at": now, "updated_at": now})
    resp = PetitionListResponse(data=[r], meta={"total": 1, "page": 1, "page_size": 20})
    assert len(resp.data) == 1
    assert resp.meta["total"] == 1


def test_list_response_rejects_missing_meta_keys():
    with pytest.raises(ValidationError, match="missing required keys"):
        PetitionListResponse(data=[], meta={"total": 0})  # missing page, page_size


# ── PetitionFilter ──────────────────────────────────────────────────────────


def test_filter_defaults():
    f = PetitionFilter()
    assert f.page == 1
    assert f.page_size == 20
    assert f.topic is None
    assert f.search is None


def test_filter_custom():
    f = PetitionFilter(topic=PetitionTopic.KLIMA, source=PetitionSource.OPENPETITION, page=3)
    assert f.topic == PetitionTopic.KLIMA
    assert f.page == 3


def test_filter_page_must_be_positive():
    with pytest.raises(ValidationError):
        PetitionFilter(page=0)


def test_filter_page_size_max_50():
    with pytest.raises(ValidationError):
        PetitionFilter(page_size=51)


def test_filter_search_max_length():
    with pytest.raises(ValidationError):
        PetitionFilter(search="x" * 201)
