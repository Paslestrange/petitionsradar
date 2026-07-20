"""PetitionsRadar scraper package.

Scrapers collect petition metadata from German petition platforms.
Each scraper implements the BaseScraper ABC with an async scrape() method.
"""

from scrapers.base import BaseScraper, ScrapeError
from scrapers.bundestag import BundestagScraper

__all__ = ["BaseScraper", "ScrapeError", "BundestagScraper"]
