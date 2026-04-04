"""Scraper registry - maps domain names to scraper classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tonghoptin.scrapers.base import BaseScraper

SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {}


def register_scraper(*domains: str):
    """Decorator to register a scraper class for one or more domains."""
    def wrapper(cls: type[BaseScraper]) -> type[BaseScraper]:
        for domain in domains:
            SCRAPER_REGISTRY[domain] = cls
        return cls
    return wrapper


def get_scraper_class(domain: str) -> type[BaseScraper]:
    """Get the scraper class for a domain, falling back to GenericScraper."""
    if domain in SCRAPER_REGISTRY:
        return SCRAPER_REGISTRY[domain]
    from tonghoptin.scrapers.generic import GenericScraper
    return GenericScraper


# Import all scrapers to trigger registration
def _register_all():
    from tonghoptin.scrapers import vnexpress  # noqa: F401
    from tonghoptin.scrapers import tuoitre  # noqa: F401
    from tonghoptin.scrapers import thanhnien  # noqa: F401
    from tonghoptin.scrapers import dantri  # noqa: F401
    from tonghoptin.scrapers import vietnamnet  # noqa: F401
    from tonghoptin.scrapers import cafef  # noqa: F401
    from tonghoptin.scrapers import cafebiz  # noqa: F401
    from tonghoptin.scrapers import vietnambusinessinsider  # noqa: F401
    from tonghoptin.scrapers import generic  # noqa: F401


_register_all()
