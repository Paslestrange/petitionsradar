"""Scraper for epetitionen.bundestag.de public petition listings.

Scrapes the public petition listing page of the German Bundestag.
Uses Playwright for JS-rendered content extraction.
"""

import asyncio
import re
from datetime import date
from typing import Optional

from playwright.async_api import Page, async_playwright

from api.models import PetitionCreate, PetitionSource, PetitionStatus, PetitionTopic
from scrapers.base import BaseScraper, ScrapeError

# Base URL for the public petition listing
LISTING_URL = "https://epetitionen.bundestag.de/petitionen/oeffentliche_petitionen.html"

# Individual petition detail URL pattern
DETAIL_URL_TEMPLATE = "https://epetitionen.bundestag.de/petitionen/_action.html?petitionId={petition_id}"


# Topic keyword mapping for classification
TOPIC_KEYWORDS: dict[PetitionTopic, list[str]] = {
    PetitionTopic.KLIMA: ["klima", "umweltschutz", "co2", "emission", "erneuerbar", "energie", "natur"],
    PetitionTopic.SOZIALES: ["sozial", "rente", "armut", "hartz", "grundsicherung", "inklusion"],
    PetitionTopic.BILDUNG: ["bildung", "schule", "universit", "studium", "lehrer", "kinderg"],
    PetitionTopic.GESUNDHEIT: ["gesundheit", "krankenhaus", "arzt", "pflege", "medizin", "impf"],
    PetitionTopic.DIGITALES: ["digital", "internet", "daten", "KI", "künstlich", "algorithm", "netz"],
    PetitionTopic.VERKEHR: ["verkehr", "auto", "bahn", "fahrrad", "tempolimit", "autobahn", "ÖPNV"],
    PetitionTopic.WOHNEN: ["wohnen", "miete", "immobil", "bau", "stadt"],
    PetitionTopic.ARBEIT: ["arbeit", "lohn", "gehalt", "mindestlohn", "arbeitszeit", "kündigung"],
    PetitionTopic.INNERES: ["polizei", "Sicherheit", "migration", "asyl", "integration", "inner"],
    PetitionTopic.AUSSEN: ["aussen", "außen", "außenpolitik", "EU", "NATO", "international"],
    PetitionTopic.UMWELT: ["umwelt", "tier", "artenschutz", "wald", "gewässer", "pestizid"],
    PetitionTopic.VERBRAUCHERSCHUTZ: ["verbraucher", "lebensmittel", "datenschutz", "DSGVO"],
}


def classify_topic(title: str, description: str) -> PetitionTopic:
    """Classify a petition into a standardized topic based on keyword matching."""
    text = (title + " " + description).lower()
    scores: dict[PetitionTopic, int] = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scores[topic] = score
    if scores:
        return max(scores, key=scores.get)
    return PetitionTopic.SONSTIGES


def parse_signature_count(text: str) -> int:
    """Parse German-formatted signature count (e.g. '12.345' -> 12345)."""
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else 0


def parse_deadline(text: str) -> Optional[date]:
    """Parse German date format (DD.MM.YYYY) to date object."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


class BundestagScraper(BaseScraper):
    """Scraper for epetitionen.bundestag.de public petitions.

    Uses Playwright to render the JS-heavy listing page and extract
    petition metadata from the public view.
    """

    REQUEST_DELAY = 3.0  # Be extra respectful with government servers

    @property
    def source(self) -> PetitionSource:
        return PetitionSource.BUNDESTAG

    async def scrape(self) -> list[PetitionCreate]:
        """Scrape public petition listings from the Bundestag e-petitions site.

        Returns list of PetitionCreate instances.
        """
        petitions: list[PetitionCreate] = []

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(user_agent=self.USER_AGENT)
                    await page.goto(LISTING_URL, wait_until="networkidle", timeout=60000)
                    await asyncio.sleep(self.REQUEST_DELAY)

                    entries = await self._extract_listing_entries(page)

                    for entry in entries:
                        try:
                            petition = await self._scrape_detail(page, entry)
                            if petition:
                                petitions.append(petition)
                            await asyncio.sleep(self.REQUEST_DELAY)
                        except Exception:
                            continue
                finally:
                    await browser.close()
        except Exception as e:
            raise ScrapeError(
                f"Failed to scrape Bundestag petitions: {e}",
                source=PetitionSource.BUNDESTAG,
            ) from e

        return petitions

    async def _extract_listing_entries(self, page: Page) -> list[dict]:
        """Extract petition entries from the listing page."""
        entries = []

        # Try structured selectors first
        rows = await page.query_selector_all(
            ".petition-list .petition-entry, "
            ".petitions-table tr, "
            "table.dataTable tbody tr, "
            "[class*='petition'] [class*='item'], "
            ".content-area a[href*='petitionId']"
        )

        if not rows:
            # Fallback: look for any links to petition detail pages
            links = await page.query_selector_all("a[href*='petitionId=']")
            seen_ids = set()
            for link in links:
                href = await link.get_attribute("href") or ""
                m = re.search(r"petitionId=(\d+)", href)
                if m and m.group(1) not in seen_ids:
                    seen_ids.add(m.group(1))
                    title = (await link.text_content() or "").strip()
                    if title:
                        entries.append({
                            "petition_id": m.group(1),
                            "title": title,
                            "signature_count": 0,
                            "deadline": None,
                            "status": "open",
                        })
            return entries

        for row in rows:
            try:
                entry = await self._parse_listinging_row(row)
                if entry:
                    entries.append(entry)
            except Exception:
                continue

        return entries

    async def _parse_listinging_row(self, row) -> Optional[dict]:
        """Parse a single listing row/entry element."""
        link = await row.query_selector("a[href*='petitionId']")
        if not link:
            return None
        href = await link.get_attribute("href") or ""
        m = re.search(r"petitionId=(\d+)", href)
        if not m:
            return None

        petition_id = m.group(1)
        title = (await link.text_content() or "").strip()
        if not title:
            return None

        sig_count = 0
        sig_el = await row.query_selector(
            "[class*='signatur'], [class*='signature'], [class*='mitzeichnung']"
        )
        if sig_el:
            sig_text = await sig_el.text_content()
            sig_count = parse_signature_count(sig_text)

        deadline = None
        date_el = await row.query_selector(
            "[class*='deadline'], [class*='frist'], [class*='datum'], time"
        )
        if date_el:
            date_text = await date_el.text_content()
            deadline = parse_deadline(date_text)

        return {
            "petition_id": petition_id,
            "title": title,
            "signature_count": sig_count,
            "deadline": deadline,
            "status": "open",
        }

    async def _scrape_detail(self, page: Page, entry: dict) -> Optional[PetitionCreate]:
        """Scrape a single petition's detail page for full description."""
        petition_id = entry["petition_id"]
        detail_url = DETAIL_URL_TEMPLATE.format(petition_id=petition_id)

        try:
            await page.goto(detail_url, wait_until="networkidle", timeout=30000)
        except Exception:
            return self._build_from_listing(entry)

        await asyncio.sleep(1)

        # Extract description
        description = ""
        desc_selectors = [
            ".petition-text",
            ".description",
            "[class*='beschreibung']",
            "[class*='anliegen']",
            ".content-area p",
            "main p",
        ]
        for sel in desc_selectors:
            el = await page.query_selector(sel)
            if el:
                description = (await el.text_content() or "").strip()
                if description:
                    break

        # Extract signature count from detail page (overrides listing)
        sig_count = entry.get("signature_count", 0)
        sig_selectors = [
            "[class*='signatur'] strong",
            "[class*='signature']",
            "[class*='mitzeichnung']",
        ]
        for sel in sig_selectors:
            el = await page.query_selector(sel)
            if el:
                text = await el.text_content()
                parsed = parse_signature_count(text)
                if parsed > 0:
                    sig_count = parsed
                    break

        # Extract signature goal
        sig_goal = None
        goal_selectors = ["[class*='ziel']", "[class*='goal']"]
        for sel in goal_selectors:
            el = await page.query_selector(sel)
            if el:
                text = await el.text_content()
                parsed = parse_signature_count(text)
                if parsed > 0:
                    sig_goal = parsed
                    break

        # Extract status
        status = PetitionStatus.OPEN
        page_text = await page.text_content("body") or ""
        if "abgeschlossen" in page_text.lower() or "closed" in page_text.lower():
            status = PetitionStatus.CLOSED
        elif "erfolgreich" in page_text.lower() or "successful" in page_text.lower():
            status = PetitionStatus.SUCCESSFUL

        # Extract deadline from detail page
        deadline = entry.get("deadline")
        if not deadline:
            deadline_selectors = [
                "[class*='frist']",
                "[class*='deadline']",
                "time[datetime]",
            ]
            for sel in deadline_selectors:
                el = await page.query_selector(sel)
                if el:
                    dt = await el.get_attribute("datetime")
                    text = await el.text_content()
                    deadline = parse_deadline(dt or text)
                    if deadline:
                        break

        title = entry.get("title", "")
        topic = classify_topic(title, description)

        return PetitionCreate(
            source=PetitionSource.BUNDESTAG,
            source_url=detail_url,
            external_id=petition_id,
            title=title[:500],
            description=description,
            topic=topic,
            signature_count=sig_count,
            signature_goal=sig_goal,
            status=status,
            deadline=deadline,
        )

    def _build_from_listing(self, entry: dict) -> PetitionCreate:
        """Build a PetitionCreate from listing-only data (no detail page)."""
        title = entry.get("title", "Unbekannte Petition")
        petition_id = entry["petition_id"]
        return PetitionCreate(
            source=PetitionSource.BUNDESTAG,
            source_url=DETAIL_URL_TEMPLATE.format(petition_id=petition_id),
            external_id=petition_id,
            title=title[:500],
            description="",
            topic=classify_topic(title, ""),
            signature_count=entry.get("signature_count", 0),
            status=PetitionStatus.OPEN,
            deadline=entry.get("deadline"),
        )
