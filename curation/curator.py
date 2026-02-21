"""
Newsletter curation engine — single Claude Haiku call to fill all sections.

Takes deduplicated articles and produces a structured JSON output that
drives the entire newsletter: chart of the day, research picks,
data-paired stories, and headline roundup.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import anthropic

from config import CLAUDE_MODEL, get_env
from curation.prompts import build_annotation_prompt, build_curation_system_prompt

logger = logging.getLogger(__name__)


def _extract_json_from_text(text: str) -> dict | None:
    """
    Extract a JSON object from Claude's response text.

    Handles markdown fences and uses balanced bracket matching
    as a fallback when direct parsing fails.

    Args:
        text: Raw response text from Claude.

    Returns:
        Parsed dict, or None on failure.
    """
    # Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    cleaned = text
    for fence in ("```json", "```"):
        cleaned = cleaned.replace(fence, "")
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Balanced bracket extraction — find outermost {...}
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None

    return None


def curate_newsletter(articles: list[dict]) -> dict | None:
    """
    Run the single curation call to produce all newsletter sections.

    Sends all deduplicated articles to Claude Haiku with the curation
    system prompt. Returns structured JSON with chart_of_the_day,
    from_the_research, in_the_data, and headlines.

    Args:
        articles: List of deduplicated article dicts (title, source, url, description).

    Returns:
        Curation result dict with 4 section keys, or None on failure.
    """
    api_key = get_env("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = build_curation_system_prompt()

    # Cap input articles to avoid bloating the prompt — the LLM only picks
    # ~20 stories, so sending 300+ is wasteful and risks hitting token limits.
    # Articles are already sorted by source priority from deduplication, so
    # truncating keeps the highest-quality sources.
    MAX_ARTICLES = 150
    if len(articles) > MAX_ARTICLES:
        logger.info("Capping articles from %d to %d for curation call", len(articles), MAX_ARTICLES)
        articles = articles[:MAX_ARTICLES]

    # Build the user message with numbered articles
    today = datetime.now().strftime("%A, %B %d, %Y")
    article_lines: list[str] = [
        f"Today is {today}. Here are {len(articles)} articles from today's sources.",
        f"Select and organize them into the 4 newsletter sections.",
        "",
    ]

    for i, article in enumerate(articles, 1):
        source = article.get("source", "Unknown")
        title = article.get("title", "Untitled")
        url = article.get("url", "")
        description = (article.get("description", "") or "")[:300]

        article_lines.append(f"{i}. [{source}] {title}")
        article_lines.append(f"   URL: {url}")
        if description:
            article_lines.append(f"   Description: {description}")
        article_lines.append("")

    user_message = "\n".join(article_lines)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract text from response
        text_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)

        full_text = "\n".join(text_parts)
        result = _extract_json_from_text(full_text)

        if result is None:
            logger.error("Failed to parse curation JSON from Claude response")
            logger.info("Raw response (first 1000 chars): %s", full_text[:1000])
            logger.info("Stop reason: %s", response.stop_reason)
            return None

        # Validate expected sections exist
        expected_sections = ["chart_of_the_day", "from_the_research", "in_the_data", "headlines"]
        for section in expected_sections:
            if section not in result:
                logger.warning("Missing section '%s' in curation result", section)
                result[section] = [] if section != "chart_of_the_day" else {}

        # Log summary
        cotd = result.get("chart_of_the_day", {})
        research_count = len(result.get("from_the_research", []))
        data_count = len(result.get("in_the_data", []))
        headline_count = len(result.get("headlines", []))

        logger.info(
            "Curation complete: COTD=%s, Research=%d, Data=%d, Headlines=%d",
            cotd.get("series_id", "none"),
            research_count,
            data_count,
            headline_count,
        )

        return result

    except Exception:
        logger.error("Curation call failed", exc_info=True)
        return None


def generate_annotation(
    series_id: str,
    series_name: str,
    latest_value: str,
    latest_date: str,
    headline: str,
) -> str:
    """
    Generate a 1-2 sentence chart annotation using Claude.

    Args:
        series_id: FRED series ID.
        series_name: Human-readable name.
        latest_value: Formatted latest value.
        latest_date: Date string.
        headline: Accompanying news headline.

    Returns:
        Annotation text, or a fallback string on failure.
    """
    api_key = get_env("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    prompt = build_annotation_prompt(
        series_id, series_name, latest_value, latest_date, headline
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        # Strip chain-of-thought leakage
        annotation = text.strip()
        # Remove bold markers that indicate self-correction
        annotation = annotation.replace("**However", "").replace("**", "")
        annotation = annotation.strip()

        if annotation:
            return annotation

    except Exception:
        logger.warning("Annotation generation failed for %s", series_id, exc_info=True)

    # Fallback
    return f"{series_name}: {latest_value} as of {latest_date}."


def generate_cotd_context(
    series_id: str,
    series_name: str,
    latest_value: str,
    latest_date: str,
    source_headline: str,
    our_headline: str,
    observations_summary: str,
) -> str:
    """
    Generate the Chart of the Day analysis, grounded in actual FRED data.

    This MUST be called AFTER fetching FRED data, not during the initial
    curation pass. The GROUND TRUTH block prevents the model from
    hallucinating values from its training data.

    Args:
        series_id: FRED series ID.
        series_name: Human-readable name.
        latest_value: Formatted latest data value.
        latest_date: Date of the latest observation.
        source_headline: The original news headline.
        our_headline: Our analytical framing headline.
        observations_summary: Brief summary of recent trend (e.g., last 6 values).

    Returns:
        3-4 sentence analytical context paragraph.
    """
    api_key = get_env("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Write 3-4 sentences of original analysis for the EconStats Daily "Chart of the Day."

## GROUND TRUTH — use ONLY these values, not your training data
Series: {series_name} ({series_id})
Current value: {latest_value} as of {latest_date}
Recent trend: {observations_summary}

## Context
Source headline: {source_headline}
Our analytical framing: {our_headline}

## Rules
- Your analysis MUST be consistent with the GROUND TRUTH data above
- If the value is HIGH relative to history, say so. If LOW, say so. Do NOT invent a narrative.
- Connect the data to the news headline — what does the chart reveal?
- Write as an economist-analyst, not a reporter
- Be specific with numbers (from the GROUND TRUTH)
- Do NOT say "the chart shows" — just state the insight
- Do NOT hedge excessively
- End with a forward-looking observation or implication

Write ONLY the 3-4 sentence paragraph, nothing else."""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        context = text.strip()
        context = context.replace("**However", "").replace("**", "").strip()

        if context:
            logger.info("Generated ground-truth COTD context for %s", series_id)
            return context

    except Exception:
        logger.warning("COTD context generation failed", exc_info=True)

    # Fallback — at least state the ground truth
    return f"{series_name} stands at {latest_value} as of {latest_date}."
