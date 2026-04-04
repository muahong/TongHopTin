"""Configuration loading and validation."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from tonghoptin.models import AppConfig, FetchMethod, SiteConfig

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.yaml"

# Default site configurations for known Vietnamese news sites
DEFAULT_SITES = [
    SiteConfig(
        name="vnexpress",
        base_url="https://vnexpress.net",
        domain="vnexpress.net",
        fetch_method=FetchMethod.REQUESTS,
        request_delay=0.5,
        max_pages=10,
        max_concurrent=5,
    ),
    SiteConfig(
        name="tuoitre",
        base_url="https://tuoitre.vn",
        domain="tuoitre.vn",
        fetch_method=FetchMethod.REQUESTS,
        request_delay=1.0,
        max_pages=5,
        max_concurrent=3,
    ),
    SiteConfig(
        name="thanhnien",
        base_url="https://thanhnien.vn",
        domain="thanhnien.vn",
        fetch_method=FetchMethod.REQUESTS,
        request_delay=1.0,
        max_pages=5,
        max_concurrent=3,
    ),
    SiteConfig(
        name="dantri",
        base_url="https://dantri.com.vn",
        domain="dantri.com.vn",
        fetch_method=FetchMethod.PLAYWRIGHT,
        request_delay=1.5,
        max_pages=1,  # Low priority - user reads homepage only
        max_concurrent=3,
    ),
    SiteConfig(
        name="vietnamnet",
        base_url="https://vietnamnet.vn",
        domain="vietnamnet.vn",
        fetch_method=FetchMethod.REQUESTS,
        request_delay=1.0,
        max_pages=5,
        max_concurrent=3,
    ),
    SiteConfig(
        name="cafef",
        base_url="https://cafef.vn",
        domain="cafef.vn",
        fetch_method=FetchMethod.REQUESTS,
        request_delay=0.8,
        max_pages=5,
        max_concurrent=3,
    ),
    SiteConfig(
        name="cafebiz",
        base_url="https://cafebiz.vn",
        domain="cafebiz.vn",
        fetch_method=FetchMethod.REQUESTS,
        request_delay=1.0,
        max_pages=3,
        max_concurrent=3,
    ),
    SiteConfig(
        name="vietnambusinessinsider",
        base_url="https://vietnambusinessinsider.vn",
        domain="vietnambusinessinsider.vn",
        fetch_method=FetchMethod.REQUESTS,
        request_delay=1.0,
        max_pages=3,
        max_concurrent=3,
    ),
]


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        logger.info(f"Config file not found at {path}, using defaults")
        return AppConfig(sites=list(DEFAULT_SITES))

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    config = AppConfig()

    # History settings
    history = data.get("history", {})
    config.chrome_history_path = history.get("chrome_path", "")
    config.brave_history_path = history.get("brave_path", "")
    config.analysis_days = history.get("analysis_days", 30)

    # Favourites
    favs = data.get("favourites", {})
    config.auto_detect_threshold = favs.get("auto_detect_threshold", 5)

    # Sites
    sites_data = data.get("sites", [])
    if sites_data:
        config.sites = []
        for s in sites_data:
            method = FetchMethod.REQUESTS
            if s.get("fetch_method") == "playwright":
                method = FetchMethod.PLAYWRIGHT
            config.sites.append(SiteConfig(
                name=s.get("name", ""),
                base_url=s.get("base_url", ""),
                domain=s.get("domain", ""),
                enabled=s.get("enabled", True),
                fetch_method=method,
                request_delay=s.get("request_delay", 1.0),
                max_pages=s.get("max_pages", 10),
                max_concurrent=s.get("max_concurrent", 5),
            ))
    else:
        config.sites = list(DEFAULT_SITES)

    # Output
    output = data.get("output", {})
    config.output_directory = output.get("directory", "./output")
    config.image_max_width = output.get("image_max_width", 800)
    config.theme = output.get("theme", "auto")

    return config


def save_config(config: AppConfig, config_path: str | Path = DEFAULT_CONFIG_PATH) -> None:
    """Save configuration to YAML file."""
    data = {
        "history": {
            "chrome_path": config.chrome_history_path,
            "brave_path": config.brave_history_path,
            "analysis_days": config.analysis_days,
        },
        "favourites": {
            "auto_detect_threshold": config.auto_detect_threshold,
        },
        "sites": [
            {
                "name": s.name,
                "base_url": s.base_url,
                "domain": s.domain,
                "enabled": s.enabled,
                "fetch_method": s.fetch_method.value,
                "request_delay": s.request_delay,
                "max_pages": s.max_pages,
                "max_concurrent": s.max_concurrent,
            }
            for s in config.sites
        ],
        "output": {
            "directory": config.output_directory,
            "image_max_width": config.image_max_width,
            "theme": config.theme,
        },
    }

    path = Path(config_path)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"Config saved to {path}")
