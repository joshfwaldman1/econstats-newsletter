"""
RSS feed source — fetches recent articles from curated economic feeds.

Ported from daily-news-tracker. Parses 17+ RSS/Atom feeds and filters
by recency (28-hour lookback window for timezone safety).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser

from config import RSS_FEEDS

logger = logging.getLogger(__name__)

# 28 hours to account for timezone differences
LOOKBACK_HOURS: int = 28


def _is_recent(entry: dict) -> bool:
    """
    Check if an RSS entry was published within the lookback window.

    Tries published_parsed first, then updated_parsed as fallback.

    Args:
        entry: A feedparser entry dict.

    Returns:
        True if the entry is recent enough to include.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    for time_field in ("published_parsed", "updated_parsed"):
        parsed_time = entry.get(time_field)
        if parsed_time:
            try:
                entry_dt = datetime.fromtimestamp(mktime(parsed_time), tz=timezone.utc)
                return entry_dt >= cutoff
            except (ValueError, OverflowError):
                continue

    # If no parseable date, include it (better to over-include than miss)
    return True


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text)


def fetch_rss_articles() -> list[dict]:
    """
    Fetch recent articles from all configured RSS feeds.

    Filters by recency, strips HTML from descriptions, and deduplicates
    by URL within the combined results.

    Returns:
        List of article dicts with keys:
            title, source, url, description, published_date
    """
    seen_urls: set[str] = set()
    articles: list[dict] = []

    for feed_config in RSS_FEEDS:
        feed_name = feed_config["name"]
        feed_url = feed_config["url"]

        try:
            feed = feedparser.parse(feed_url)

            if feed.bozo and feed.bozo_exception:
                logger.debug(
                    "RSS [%s] bozo warning: %s",
                    feed_name,
                    str(feed.bozo_exception)[:100],
                )

            feed_count = 0
            for entry in feed.entries:
                if not _is_recent(entry):
                    continue

                url = entry.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title = entry.get("title", "").strip()
                if not title:
                    continue

                # Extract and clean description
                description = entry.get("summary", "") or entry.get("description", "")
                description = _strip_html(description)[:500]

                # Extract published date
                published_date = entry.get("published", "") or entry.get("updated", "")

                articles.append({
                    "title": title,
                    "source": feed_name,
                    "url": url,
                    "description": description,
                    "published_date": published_date,
                })
                feed_count += 1

            logger.info("RSS [%s]: %d recent articles", feed_name, feed_count)

        except Exception:
            logger.warning("RSS feed '%s' failed", feed_name, exc_info=True)
            continue

    logger.info("RSS total: %d unique articles", len(articles))
    return articles
