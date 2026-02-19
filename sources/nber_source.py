"""
NBER working papers source — discovers new papers and extracts PDF URLs.

Parses the NBER new papers RSS feed to find recently published working
papers. Extracts the PDF download URL for each paper so we can later
extract charts from the PDFs using PyMuPDF + Claude Vision.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import requests

from config import NBER_PAPERS_RSS

logger = logging.getLogger(__name__)

# NBER paper page pattern: https://www.nber.org/papers/w12345
NBER_PAPER_URL_RE = re.compile(r"https?://www\.nber\.org/papers/(w\d+)")

# 72 hours — NBER publishes weekly batches on Mondays
LOOKBACK_HOURS: int = 72


def _extract_paper_id(url: str) -> str | None:
    """
    Extract the NBER paper ID (e.g., 'w33456') from a URL.

    Args:
        url: URL string from an RSS entry.

    Returns:
        Paper ID like 'w33456', or None if not an NBER paper URL.
    """
    match = NBER_PAPER_URL_RE.search(url)
    return match.group(1) if match else None


def _build_pdf_url(paper_id: str) -> str:
    """
    Construct the direct PDF download URL for an NBER paper.

    NBER PDFs follow a predictable URL pattern.

    Args:
        paper_id: Paper identifier like 'w33456'.

    Returns:
        Direct PDF URL.
    """
    return f"https://www.nber.org/system/files/working_papers/{paper_id}/{paper_id}.pdf"


def _is_recent(entry: dict) -> bool:
    """Check if an RSS entry is within the lookback window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    for time_field in ("published_parsed", "updated_parsed"):
        parsed_time = entry.get(time_field)
        if parsed_time:
            try:
                entry_dt = datetime.fromtimestamp(mktime(parsed_time), tz=timezone.utc)
                return entry_dt >= cutoff
            except (ValueError, OverflowError):
                continue

    return True  # Include if no date available


def _verify_pdf_exists(pdf_url: str) -> bool:
    """
    Quick HEAD request to verify the PDF is accessible.

    Args:
        pdf_url: URL to check.

    Returns:
        True if the PDF responds with HTTP 200.
    """
    try:
        resp = requests.head(pdf_url, timeout=10, allow_redirects=True)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def fetch_nber_papers() -> list[dict]:
    """
    Fetch recent NBER working papers with PDF URLs.

    Parses the NBER RSS feed, extracts paper IDs, constructs PDF URLs,
    and verifies PDF accessibility.

    Returns:
        List of paper dicts with keys:
            title, source, url, description, published_date,
            paper_id, pdf_url, pdf_verified
    """
    papers: list[dict] = []

    try:
        feed = feedparser.parse(NBER_PAPERS_RSS)

        if feed.bozo and feed.bozo_exception:
            logger.debug("NBER RSS bozo: %s", str(feed.bozo_exception)[:100])

        for entry in feed.entries:
            if not _is_recent(entry):
                continue

            url = entry.get("link", "")
            title = entry.get("title", "").strip()
            if not url or not title:
                continue

            # Extract paper ID
            paper_id = _extract_paper_id(url)
            if not paper_id:
                # Still include non-paper entries (blog posts, etc.)
                papers.append({
                    "title": title,
                    "source": "NBER",
                    "url": url,
                    "description": (entry.get("summary", "") or "")[:500],
                    "published_date": entry.get("published", ""),
                    "paper_id": None,
                    "pdf_url": None,
                    "pdf_verified": False,
                })
                continue

            # Build and verify PDF URL
            pdf_url = _build_pdf_url(paper_id)
            pdf_verified = _verify_pdf_exists(pdf_url)

            description = entry.get("summary", "") or entry.get("description", "")
            # Clean HTML tags
            description = re.sub(r"<[^>]+>", "", description)[:500]

            papers.append({
                "title": title,
                "source": "NBER",
                "url": url,
                "description": description,
                "published_date": entry.get("published", ""),
                "paper_id": paper_id,
                "pdf_url": pdf_url if pdf_verified else None,
                "pdf_verified": pdf_verified,
            })

            logger.debug(
                "NBER paper %s: PDF %s",
                paper_id,
                "verified" if pdf_verified else "not found",
            )

        logger.info(
            "NBER: %d papers (%d with verified PDFs)",
            len(papers),
            sum(1 for p in papers if p.get("pdf_verified")),
        )

    except Exception:
        logger.warning("NBER source failed", exc_info=True)

    return papers
