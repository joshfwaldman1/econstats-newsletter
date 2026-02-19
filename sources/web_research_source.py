"""
Web research source — uses Claude's web search tool to discover
recent economic research papers and analysis.

Ported from daily-news-tracker. Makes a single Claude API call
with the web_search tool to find papers from NBER, Brookings,
PIIE, IMF, Fed, BIS, and other research institutions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import anthropic

from config import CLAUDE_MODEL, get_env

logger = logging.getLogger(__name__)


def _extract_json_from_text(text: str) -> list[dict]:
    """
    Extract a JSON array from Claude's response text.

    Handles markdown fences, balanced bracket matching, and
    other common formatting issues.

    Args:
        text: Raw text from Claude's response.

    Returns:
        Parsed list of article dicts.
    """
    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    cleaned = text
    for fence in ("```json", "```"):
        cleaned = cleaned.replace(fence, "")
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Balanced bracket extraction — find the outermost [...]
    start = text.find("[")
    if start == -1:
        return []

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return []

    return []


def fetch_web_research_articles() -> list[dict]:
    """
    Use Claude's web search tool to discover recent research papers.

    Makes one Claude API call with the web_search tool (max 5 searches).
    Targets papers from the last 2-3 days from major research institutions.

    Returns:
        List of article dicts with keys:
            title, source, url, description, published_date
    """
    api_key = get_env("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""Search for recent economic research papers and policy analysis published
in the last 2-3 days (today is {today}). Look for papers from:
- NBER (National Bureau of Economic Research)
- Brookings Institution
- Peterson Institute (PIIE)
- AEI (American Enterprise Institute)
- IMF working papers
- Federal Reserve (FEDS Notes, working papers)
- BIS (Bank for International Settlements)
- CEPR / VoxEU columns
- SSRN economics papers

Return 5-15 items as a JSON array. Each item should have:
- "title": paper/article title
- "source": institution name
- "url": direct URL to the paper
- "description": 1-2 sentence summary of the paper's findings
- "published_date": publication date if available

Return ONLY the JSON array, no other text."""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 5,
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text from response blocks
        text_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)

        full_text = "\n".join(text_parts)
        articles = _extract_json_from_text(full_text)

        # Normalize the articles
        normalized: list[dict] = []
        for item in articles:
            if isinstance(item, dict) and item.get("title") and item.get("url"):
                normalized.append({
                    "title": item["title"],
                    "source": item.get("source", "Research"),
                    "url": item["url"],
                    "description": item.get("description", "")[:500],
                    "published_date": item.get("published_date", ""),
                })

        logger.info("Web research: discovered %d papers", len(normalized))
        return normalized

    except Exception:
        logger.warning("Web research source failed", exc_info=True)
        return []
