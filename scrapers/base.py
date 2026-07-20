"""Abstract base class for all petition scrapers."""

from abc import ABC, abstractmethod
from typing import Optional

import httpx

from api.models import PetitionCreate, PetitionSource


class ScrapeError(Exception):
    """Raised when a scraper encounters an unrecoverable error."""

    def __init__(self, message: str, source: PetitionSource, status_code: Optional[int] = None):
        self.source = source
        self.status_code = status_code
        super().__init__(message)


class BaseScraper(ABC):
    """Abstract base class for petition scrapers.

    Subclasses must implement:
        - source: PetitionSource property identifying the platform
        - scrape(): async method returning list[PetitionCreate]

    Provides:
        - Rate limiting via configurable delay between page loads
        - HTTP client lifecycle management
        - Common user-agent and headers
    """

    # Rate limiting: seconds between page loads to be respectful
    REQUEST_DELAY: float = 2.0

    # Browser user-agent
    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )

    def __init__(self, request_delay: Optional[float] = None):
        """Initialize scraper with optional custom request delay."""
        if request_delay is not None:
            self.REQUEST_DELAY = request_delay

    @property
    @abstractmethod
    def source(self) -> PetitionSource:
        """Identify which platform this scraper targets."""
        ...

    @abstractmethod
    async def scrape(self) -> list[PetitionCreate]:
        """Scrape petition listings from the source platform.

        Returns:
            List of PetitionCreate instances ready for database insertion.

        Raises:
            ScrapeError: If the source is unreachable or returns unexpected content.
        """
        ...

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Create an HTTP client with standard headers."""
        return httpx.AsyncClient(
            headers={"User-Agent": self.USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source={self.source.value}>"
