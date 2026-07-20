"""Tests for scraper package — base ABC and Bundestag scraper with mocked responses."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from api.models import PetitionCreate, PetitionSource, PetitionStatus, PetitionTopic
from scrapers.base import BaseScraper, ScrapeError
from scrapers.bundestag import (
    BundestagScraper,
    classify_topic,
    parse_deadline,
    parse_signature_count,
)


# ── Helper functions ────────────────────────────────────────────────────────


class TestParseSignatureCount:
    def test_german_format(self):
        assert parse_signature_count("12.345") == 12345

    def test_plain_number(self):
        assert parse_signature_count("5000") == 5000

    def test_with_text(self):
        assert parse_signature_count("25.000 Mitzeichnungen") == 25000

    def test_empty_string(self):
        assert parse_signature_count("") == 0

    def test_no_digits(self):
        assert parse_signature_count("keine") == 0

    def test_large_number(self):
        assert parse_signature_count("1.234.567") == 1234567


class TestParseDeadline:
    def test_german_date(self):
        assert parse_deadline("30.07.2026") == date(2026, 7, 30)

    def test_date_with_text(self):
        assert parse_deadline("Frist: 15.12.2026") == date(2026, 12, 15)

    def test_single_digit_day_month(self):
        assert parse_deadline("1.3.2026") == date(2026, 3, 1)

    def test_empty_string(self):
        assert parse_deadline("") is None

    def test_none(self):
        assert parse_deadline(None) is None

    def test_invalid_date(self):
        assert parse_deadline("32.13.2026") is None

    def test_no_date_in_text(self):
        assert parse_deadline("kein Datum hier") is None


class TestClassifyTopic:
    def test_klima(self):
        result = classify_topic("Tempolimit 130", "Wir fordern ein Tempolimit auf Autobahnen für Klima")
        assert result in (PetitionTopic.VERKEHR, PetitionTopic.KLIMA)

    def test_bildung(self):
        assert classify_topic("Bildung verbessern", "Schule und Universität brauchen mehr Geld") == PetitionTopic.BILDUNG

    def test_gesundheit(self):
        assert classify_topic("Krankenhausreform", "Die Pflege im Krankenhaus muss verbessert werden") == PetitionTopic.GESUNDHEIT

    def test_digital(self):
        assert classify_topic("Digitale Infrastruktur", "Internet für alle, Datenschutz stärken") == PetitionTopic.DIGITALES

    def test_unknown_defaults_to_sonstiges(self):
        assert classify_topic("Irgendwas", "völlig unbekanntes Thema xyzabc") == PetitionTopic.SONSTIGES

    def test_multiple_topics_returns_highest_score(self):
        title = "Klima und Verkehr"
        desc = "Tempolimit für Klimaschutz auf Autobahnen einführen"
        result = classify_topic(title, desc)
        assert result in (PetitionTopic.KLIMA, PetitionTopic.VERKEHR)


# ── BaseScraper ABC ─────────────────────────────────────────────────────────


class TestBaseScraper:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseScraper()

    def test_concrete_subclass(self):
        class MyScraper(BaseScraper):
            @property
            def source(self):
                return PetitionSource.BUNDESTAG

            async def scrape(self):
                return []

        s = MyScraper()
        assert s.source == PetitionSource.BUNDESTAG
        assert repr(s) == "<MyScraper source=bundestag>"

    def test_custom_request_delay(self):
        class MyScraper(BaseScraper):
            @property
            def source(self):
                return PetitionSource.BUNDESTAG

            async def scrape(self):
                return []

        s = MyScraper(request_delay=5.0)
        assert s.REQUEST_DELAY == 5.0


# ── ScrapeError ─────────────────────────────────────────────────────────────


class TestScrapeError:
    def test_scrape_error_attributes(self):
        err = ScrapeError("test error", source=PetitionSource.BUNDESTAG, status_code=503)
        assert err.source == PetitionSource.BUNDESTAG
        assert err.status_code == 503
        assert "test error" in str(err)

    def test_scrape_error_no_status(self):
        err = ScrapeError("timeout", source=PetitionSource.OPENPETITION)
        assert err.status_code is None


# ── BundestagScraper ────────────────────────────────────────────────────────


class TestBundestagScraper:
    def test_source_property(self):
        s = BundestagScraper()
        assert s.source == PetitionSource.BUNDESTAG

    def test_default_request_delay(self):
        s = BundestagScraper()
        assert s.REQUEST_DELAY == 3.0

    def test_custom_delay(self):
        s = BundestagScraper(request_delay=10.0)
        assert s.REQUEST_DELAY == 10.0

    def test_repr(self):
        s = BundestagScraper()
        assert "BundestagScraper" in repr(s)
        assert "bundestag" in repr(s)

    def test_build_from_listing(self):
        s = BundestagScraper()
        entry = {
            "petition_id": "12345",
            "title": "Test Petition",
            "signature_count": 500,
            "deadline": date(2026, 8, 1),
            "status": "open",
        }
        petition = s._build_from_listing(entry)
        assert isinstance(petition, PetitionCreate)
        assert petition.external_id == "12345"
        assert petition.title == "Test Petition"
        assert petition.source == PetitionSource.BUNDESTAG
        assert petition.source_url == "https://epetitionen.bundestag.de/petitionen/_action.html?petitionId=12345"
        assert petition.signature_count == 500
        assert petition.deadline == date(2026, 8, 1)


class TestBundestagScraperScrape:
    """Integration-style tests using mocked Playwright responses."""

    @pytest.mark.asyncio
    async def test_scrape_returns_petitions(self):
        """Test scrape with mocked Playwright page returning petition data."""
        s = BundestagScraper(request_delay=0)

        # Mock link element on listing page
        mock_link = AsyncMock()
        mock_link.get_attribute = AsyncMock(return_value="/petition?petitionId=99999")
        mock_link.text_content = AsyncMock(return_value="Mock Petition Title")

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        # Listing: no structured rows, fallback to links
        mock_page.query_selector_all = AsyncMock(side_effect=[
            [],  # no structured rows
            [mock_link],  # fallback links
        ])
        # Detail page: description element
        mock_desc_el = AsyncMock()
        mock_desc_el.text_content = AsyncMock(return_value="Description about klima themes.")
        mock_page.query_selector = AsyncMock(return_value=mock_desc_el)
        mock_page.text_content = AsyncMock(return_value="Some page text")

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("scrapers.bundestag.async_playwright", return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_pw),
            __aexit__=AsyncMock(return_value=None),
        )):
            results = await s.scrape()

        assert isinstance(results, list)
        for p in results:
            assert isinstance(p, PetitionCreate)
            assert p.source == PetitionSource.BUNDESTAG

    @pytest.mark.asyncio
    async def test_scrape_raises_scrape_error_on_failure(self):
        """Test that ScrapeError is raised when Playwright fails catastrophically."""
        s = BundestagScraper(request_delay=0)

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(side_effect=RuntimeError("Browser crashed"))

        with patch("scrapers.bundestag.async_playwright", return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_pw),
            __aexit__=AsyncMock(return_value=None),
        )):
            with pytest.raises(ScrapeError) as exc_info:
                await s.scrape()
            assert exc_info.value.source == PetitionSource.BUNDESTAG

    @pytest.mark.asyncio
    async def test_scrape_handles_empty_listing(self):
        """Test scrape with empty listing page (no petitions found)."""
        s = BundestagScraper(request_delay=0)

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("scrapers.bundestag.async_playwright", return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_pw),
            __aexit__=AsyncMock(return_value=None),
        )):
            results = await s.scrape()

        assert results == []

    @pytest.mark.asyncio
    async def test_scrape_detail_page_failure_falls_back(self):
        """Test that detail page failure falls back gracefully."""
        s = BundestagScraper(request_delay=0)

        mock_link = AsyncMock()
        mock_link.get_attribute = AsyncMock(return_value="/petition?petitionId=54321")
        mock_link.text_content = AsyncMock(return_value="Fallback Petition")

        mock_page = AsyncMock()
        # Listing loads OK, detail page times out
        mock_page.goto = AsyncMock(side_effect=[
            None,
            Exception("Timeout"),
        ])
        mock_page.query_selector_all = AsyncMock(side_effect=[
            [],
            [mock_link],
        ])

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("scrapers.bundestag.async_playwright", return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_pw),
            __aexit__=AsyncMock(return_value=None),
        )):
            results = await s.scrape()
            assert isinstance(results, list)
