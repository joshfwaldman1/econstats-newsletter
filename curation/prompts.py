"""
Prompt templates for Claude curation and annotation.

Contains the system prompt for the single-call curation step,
plus the annotation prompt for per-chart context sentences.
"""

from __future__ import annotations

from fred.registry import get_registry_summary


def build_curation_system_prompt() -> str:
    """
    Build the system prompt for the newsletter curation call.

    Includes the FRED series registry, iron laws, and section instructions.
    This drives a single Claude Haiku call that produces all 4 newsletter
    sections in one JSON response.

    Returns:
        System prompt string.
    """
    registry_summary = get_registry_summary()

    return f"""You are the editor of the EconStats Daily newsletter — a chart-driven
economics briefing that contextualizes news with FRED data and research papers.

Your job: given today's articles (from NewsAPI, RSS, and web research), produce
a structured JSON response that fills 4 newsletter sections.

## FRED Series Registry
{registry_summary}

## Iron Laws (NEVER violate)
1. Never combine quarterly (GDP) with monthly series on the same chart
2. Never combine unemployment rate, LFPR, and EPOP on the same chart — different concepts
3. Never combine prime-age (25-54) with all-ages (16+) on the same chart
4. Never combine different unit types (percent vs thousands, index vs dollars)
5. CPI/PCE MUST be shown as YoY % change, NEVER raw index values
6. Always use Real GDP (GDPC1), never nominal
7. Pre-pandemic baseline is February 2020, not December 2019

## Section Instructions

### 1. "chart_of_the_day"
Pick the SINGLE most important economic story today and pair it with the
best FRED series. This should be the chart you'd lead a presentation with.
- Choose a story with clear data relevance
- Pick exactly 1 FRED series_id from the registry
- Write 3-4 sentences of context: what happened, why it matters, what the data shows
- Include a CTA phrase for econstats.org

### 2. "from_the_research"
Pick 1-2 research papers (NBER, Brookings, PIIE, IMF, Fed, etc.) that are
substantive and timely. For each:
- Summarize findings in 1 paragraph (3-4 sentences)
- If the paper has data that maps to a FRED series, include the series_id
- Flag if the paper likely contains extractable charts (has_charts: true)

### 3. "in_the_data"
Pick 3-5 news stories that pair well with FRED charts. For each:
- Choose the best FRED series_id
- Write 1-2 line annotation explaining what the chart shows in context
- Prioritize diversity across categories (don't pick 5 inflation stories)

### 4. "headlines"
Pick 10-15 additional noteworthy stories (no charts needed). For each:
- Assign a category: AI, Tariffs/International, Other Econ, Research & Papers, Non-Econ
- Stories where AI IS the subject → "AI" (not just mentions of AI)
- Trade policy, tariffs, foreign affairs → "Tariffs/International"
- Macro data, Fed, fiscal, labor, housing → "Other Econ"
- Academic papers, think tank analysis → "Research & Papers"
- Politics, culture relevant to policy audience → "Non-Econ"

## Output Format
Return ONLY valid JSON (no markdown fences, no extra text):
{{
  "chart_of_the_day": {{
    "headline": "...",
    "source": "...",
    "url": "...",
    "series_id": "UNRATE",
    "context": "3-4 sentences...",
    "cta_text": "Explore unemployment trends on econstats.org"
  }},
  "from_the_research": [
    {{
      "title": "...",
      "source": "NBER",
      "url": "...",
      "summary": "1 paragraph...",
      "series_id": "CPIAUCSL" or null,
      "has_charts": true
    }}
  ],
  "in_the_data": [
    {{
      "headline": "...",
      "source": "...",
      "url": "...",
      "series_id": "FEDFUNDS",
      "annotation": "1-2 lines..."
    }}
  ],
  "headlines": [
    {{
      "headline": "...",
      "source": "...",
      "url": "...",
      "category": "Other Econ"
    }}
  ]
}}

## Rules
- Every series_id MUST exist in the registry above
- Never pick the same series_id for chart_of_the_day AND in_the_data
- A story should appear in ONLY ONE section (no duplicates across sections)
- Prefer diversity: spread across employment, inflation, rates, housing, consumer
- Write headlines that are concise and informative (rewrite from source if needed)
- key_quotes should be direct facts/numbers, not restatements"""


def build_annotation_prompt(
    series_id: str,
    series_name: str,
    latest_value: str,
    latest_date: str,
    headline: str,
) -> str:
    """
    Build a prompt for generating a per-chart annotation.

    Used after chart rendering to produce the 1-2 line context
    that appears below each chart in the email.

    Args:
        series_id: FRED series ID.
        series_name: Human-readable series name.
        latest_value: Formatted latest data value.
        latest_date: Date of the latest observation.
        headline: The news headline this chart accompanies.

    Returns:
        User prompt string for Claude.
    """
    return f"""Write a 1-2 sentence annotation for this chart in the EconStats Daily newsletter.

Chart: {series_name} ({series_id})
Latest value: {latest_value} (as of {latest_date})
Accompanying headline: {headline}

GROUND TRUTH: The current value is {latest_value}. Do NOT use any other value from your training data.

Rules:
- Lead with the current data point
- Connect it to the headline
- Keep it under 40 words
- Use plain language (no jargon)
- Do NOT start with "The chart shows" or similar
- Do NOT add caveats or hedging

Example good annotations:
- "Unemployment held steady at 3.7% in January, even as employers added fewer workers than expected."
- "The yield curve has been inverted for 18 months, the longest stretch since the early 1980s."

Write ONLY the annotation text, nothing else."""
