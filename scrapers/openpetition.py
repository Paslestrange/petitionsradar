"""Scraper for openPetition.de public listings."""

import re
from datetime import datetime
from typing import AsyncIterator
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Browser, Page

from api.models import PetitionCreate, PetitionSource, PetitionStatus, PetitionTopic
from scrapers.base import BaseScraper, ScraperError


# Mapping from openPetition categories to standardized topics
TOPIC_MAP = {
    "umwelt": PetitionTopic.UMWELT,
    "klima": PetitionTopic.KLIMA,
    "soziales": PetitionTopic.SOCIALES,
    "gesellschaft": PetitionTopic.SOCIALES,
    "bildung": PetitionTopic.BILDUNG,
    "gesundheit": PetitionTopic.GESUNDHEIT,
    "digitales": PetitionTopic.DIGITALES,
    "verkehr": PetitionTopic.VERKEHR,
    "wohnen": PetitionTopic.WOHNEN,
    "arbeit": PetitionTopic.ARBERT,
    "wirtschaft": PetitionTopic.ARBERT,
    "inneres": PetitionTopic.INNERES,
    "aussen": PetitionTopic.AUSSEN,
    "verbraucherschutz": PetitionTopic.VERBRAUCHERSCHUTZ,
    "politik": PetitionTopic.SONSTIGES,
}


def _parse_signature_count(text: str) -> int:
    """Parse signature count from text like '12.345 Unterschriften'."""
    if not text:
        return 0
    cleaned = text.replace(".", "").replace(",", "")
    match = re.search(r"(\d+)", cleaned)
    return int(match.group(1)) if match else 0


def _parse_deadline(text: str):
    """Parse deadline from text like 'läuft ab am 30.07.2026'."""
    if not text:
        return None
    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day).date()
        except ValueError:
            pass
    return None


def _extract_topic(category: str) -> PetitionTopic:
    """Map openPetition category to standardized topic."""
    category_lower = category.lower().strip()
    for key, topic in TOPIC_MAP.items():
        if key in category_lower:
            return topic
    return PetitionTopic.SONSTIGES


def _extract_status(status_text: str) -> PetitionStatus:
    """Determine petition status from status text."""
    if not status_text:
        return PetitionStatus.OPEN
    status_lower = status_text.lower()
    if "erfolgreich" in status_lower or "abgeschlossen mit erfolg" in status_lower:
        return PetitionStatus.SUCCESSFUL
    if "gescheitert" in status_lower or "abgelehnt" in status_lower:
        return PetitionStatus.FAILED
    if any(w in status_lower for w in ("beendet", "geschlossen", "abgeschlossen")):
        return PetitionStatus.CLOSED
    return PetitionStatus.OPEN


class OpenPetitionScraper(BaseScraper):
    """Scraper for openPetition.de public petition listings."""

    BASE_URL = "https://www.openpetition.de"
    LIST_URL = f"{BASE_URL}/petitionen"

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._browser: Browser | None = None
        self._playwright = None

    async def _ensure_browser(self):
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self._headless)

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def scrape(self) -> AsyncIterator[PetitionCreate]:
        await self._ensure_browser()
        page = await self._browser.new_page()

        try:
            await page.goto(self.LIST_URL, wait_until="networkidle")
            await page.wait_for_selector(
                ".petition-card, .petition-list-item", timeout=30000
            )
            cards = await page.query_selector_all(
                ".petition-card, .petition-list-item, article"
            )

            for card in cards:
                try:
                    petition = await self._parse_card(card)
                    if petition:
                        yield petition
                except Exception:
                    continue

        except Exception as e:
            raise ScraperError(f"Failed to scrape openPetition: {e}") from e
        finally:
            await page.close()

    async def _parse_card(self, card) -> PetitionCreate | None:
        """Parse a single petition card element."""
        # Title
        title_elem = await card.query_selector("h2, h3, .petition-title, a.title")
        if not title_elem:
            return None
        title = (await title_elem.text_content() or "").strip()
        if not title:
            return None

        # URL and external_id
        link_elem = await card.query_selector("a[href*='/petition/']")
        if not link_elem:
            return None
        href = await link_elem.get_attribute("href") or ""
        source_url = urljoin(self.BASE_URL, href)

        id_match = re.search(r"/petition/(\d+)", source_url)
        external_id = id_match.group(1) if id_match else href.rstrip("/").split("/")[-1]

        # Description
        desc_elem = await card.query_selector(
            ".description, .petition-description, p"
        )
        description = (await desc_elem.text_content() or "").strip() if desc_elem else ""

        # Signature count
        sig_elem = await card.query_selector(
            ".signatures, .signature-count, .count"
        )
        sig_text = (await sig_elem.text_content() or "") if sig_elem else ""
        signature_count = _parse_signature_count(sig_text)

        # Signature goal
        goal_elem = await card.query_selector(".goal, .signature-goal, .target")
        goal_text = (await goal_elem.text_content() or "") if goal_elem else ""
        signature_goal = _parse_signature_count(goal_text) if goal_text else None

        # Deadline
        deadline_elem = await card.query_selector(".deadline, .end-date, .time-left")
        deadline_text = (await deadline_elem.text_content() or "") if deadline_elem else ""
        deadline = _parse_deadline(deadline_text)

        # Status
        status_elem = await card.query_selector(".status, .petition-status")
        status_text = (await status_elem.text_content() or "") if status_elem else ""
        status = _extract_status(status_text)

        # Topic/category
        category_elem = await card.query_selector(".category, .topic, .tag")
        category_text = (await category_elem.text_content() or "sonstiges") if category_elem else "sonstiges"
        topic = _extract_topic(category_text)

        return PetitionCreate(
            source=PetitionSource.OPENPETITION,
            source_url=source_url,
            external_id=external_id,
            title=title[:500],
            description=description,
            topic=topic,
            signature_count=signature_count,
            signature_goal=signature_goal,
            status=status,
            deadline=deadline,
        )
