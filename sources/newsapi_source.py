"""
NewsAPI source — fetches recent economics/AI/policy articles.

Ported from daily-news-tracker with minimal changes.
Uses the NewsAPI "everything" endpoint with category-specific queries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from newsapi import NewsApiClient

from config import NEWSAPI_QUERIES, get_env

logger = logging.getLogger(__name__)


def _yesterday_iso() -> str:
    """Return yesterday's date in ISO format for NewsAPI date filtering."""
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def fetch_newsapi_articles() -> list[dict]:
    """
    Fetch recent articles from NewsAPI across all configured queries.

    Runs one API call per query in NEWSAPI_QUERIES (5 total).
    Deduplicates within results by URL.

    Returns:
        List of article dicts with keys:
            title, source, url, description, published_date
    """
    api_key = get_env("NEWSAPI_KEY")
    client = NewsApiClient(api_key=api_key)

    seen_urls: set[str] = set()
    articles: list[dict] = []
    from_date = _yesterday_iso()

    for query_config in NEWSAPI_QUERIES:
        query_name = query_config["name"]
        query_text = query_config["query"]

        try:
            response = client.get_everything(
                q=query_text,
                from_param=from_date,
                language="en",
                sort_by="relevancy",
                page_size=20,
            )

            for article in response.get("articles", []):
                url = article.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                source_name = article.get("source", {}).get("name", "Unknown")
                title = article.get("title", "").strip()

                # Skip articles with placeholder titles
                if not title or title == "[Removed]":
                    continue

                description = (article.get("description") or "")[:500]

                articles.append({
                    "title": title,
                    "source": source_name,
                    "url": url,
                    "description": description,
                    "published_date": article.get("publishedAt", ""),
                })

            logger.info(
                "NewsAPI [%s]: fetched %d articles",
                query_name,
                len(response.get("articles", [])),
            )

        except Exception:
            logger.warning("NewsAPI query '%s' failed", query_name, exc_info=True)
            continue

    logger.info("NewsAPI total: %d unique articles", len(articles))
    return articles
