"""
Chief Economist review agent — final quality gate before the newsletter ships.

Plays the role of a senior economist (think Jason Furman or Jan Hatzius)
reviewing the newsletter for factual errors, stale data references,
misleading framing, and analytical quality.

Called after all ground-truth data has been injected (Step 9) and before
the email is built (Step 10). The reviewer can rewrite any text field.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import anthropic

from config import get_env

logger = logging.getLogger(__name__)

# Use Sonnet for the reviewer — more capable than Haiku at catching
# subtle factual errors and evaluating analytical quality.
REVIEWER_MODEL: str = "claude-sonnet-4-20250514"


def _build_review_prompt(
    chart_of_the_day: dict,
    from_the_research: list[dict],
    in_the_data: list[dict],
    headlines: list[dict],
    ground_truth_summary: str,
) -> str:
    """
    Build the full review prompt with all newsletter content and ground-truth data.

    Args:
        chart_of_the_day: COTD section dict.
        from_the_research: Research section list.
        in_the_data: Data stories list.
        headlines: Headlines roundup list.
        ground_truth_summary: Formatted string of all FRED data fetched.

    Returns:
        User prompt string for the reviewer.
    """
    # Serialize the current newsletter content
    newsletter_payload = json.dumps(
        {
            "chart_of_the_day": chart_of_the_day,
            "from_the_research": from_the_research,
            "in_the_data": in_the_data,
            "headlines": headlines,
        },
        indent=2,
        default=str,
    )

    today = datetime.now().strftime("%A, %B %d, %Y")

    return f"""You are the Chief Economist reviewing the EconStats Daily newsletter
before it ships to subscribers. Today is {today}.

You are a former CEA chair / chief economist at a major bank. You have the
instincts of Jason Furman and the precision of Jan Hatzius. Your job is to
catch errors that would embarrass us in front of a sophisticated audience
of economists, policy professionals, and finance practitioners.

## GROUND TRUTH — Actual FRED data fetched today
{ground_truth_summary}

## NEWSLETTER CONTENT TO REVIEW
{newsletter_payload}

## YOUR REVIEW CHECKLIST

### 1. FACTUAL ACCURACY (most important)
- Do any annotations or context paragraphs cite data values that CONTRADICT
  the ground truth above? (e.g., wrong GDP quarter, wrong inflation rate,
  stale unemployment number)
- Are any quarter/month references wrong? (e.g., saying "Q3" when the latest
  GDP data is Q4, or saying "January" when the data is from December)
- Are any directional claims wrong? (e.g., saying "rose" when the data shows a decline)

### 2. ANALYTICAL QUALITY
- Does the Chart of the Day context actually provide insight beyond the headline?
- Are the annotations substantive or just restating the obvious?
- Would a reader of the FT or WSJ learn something from this?

### 3. FRAMING & ATTRIBUTION
- Are direct quotes properly attributed with quotation marks?
- Is anything presented as our analysis that is actually just parroting a headline?
- Are data sources properly attributed to BLS/BEA/Fed (not "FRED")?

### 4. IRON LAW VIOLATIONS
- Quarterly + monthly data mixed on same chart concept?
- Unemployment rate conflated with LFPR or EPOP?
- CPI/PCE shown as raw index instead of YoY%?
- Nominal GDP used instead of Real GDP?

## OUTPUT FORMAT
Return ONLY valid JSON (no markdown fences):
{{
  "verdict": "pass" or "fail",
  "issues_found": [
    {{
      "severity": "critical" or "warning",
      "section": "chart_of_the_day" or "in_the_data" or "from_the_research" or "headlines",
      "field": "context" or "annotation" or "headline" etc.,
      "item_index": 0,
      "problem": "Brief description of the error",
      "fix": "Corrected text to replace the problematic field"
    }}
  ],
  "reviewer_notes": "1-2 sentence overall assessment"
}}

Rules:
- "critical" = factual error that MUST be fixed (wrong numbers, wrong quarter, wrong direction)
- "warning" = quality issue worth fixing but not embarrassing if shipped
- verdict = "fail" only if there are critical issues
- For each critical issue, you MUST provide a "fix" with corrected text
- For warnings, "fix" is optional
- If everything looks good, return verdict "pass" with empty issues_found
- Be specific — don't flag vague concerns, flag concrete errors with fixes"""


REVIEW_SYSTEM_PROMPT: str = """You are a meticulous Chief Economist reviewer. Your
reputation depends on never letting a factual error slip through. You are reviewing
a daily economics newsletter that goes to sophisticated readers.

You ONLY flag concrete, verifiable issues — not stylistic preferences. When you
flag something, you provide the exact fix. You are not a copyeditor; you are a
fact-checker and quality controller.

IMPORTANT: If the ground truth data says the latest value is X, and the newsletter
says Y, that is ALWAYS a critical error. The ground truth data is authoritative."""


def build_ground_truth_summary(
    series_data_map: dict,
    chart_results: dict,
    registry_lookup: callable,
) -> str:
    """
    Build a human-readable summary of all FRED data fetched for this run.

    This gives the reviewer the authoritative values to check against.

    Args:
        series_data_map: Dict of series_id → FredData objects.
        chart_results: Dict of series_id → chart render results.
        registry_lookup: The fred.registry.lookup function.

    Returns:
        Formatted multi-line string of ground truth data.
    """
    lines: list[str] = []

    for series_id, data in series_data_map.items():
        reg = registry_lookup(series_id)
        name = reg.display_name or reg.name if reg else series_id

        # Get latest value from chart results (already formatted)
        result = chart_results.get(series_id, {})
        latest_val = result.get("latest_value", "N/A")
        latest_date = result.get("latest_date", "N/A")

        # Also show the last few raw observations for context
        valid_obs = [o for o in data.observations if o.value is not None] if data else []
        recent = valid_obs[-4:] if len(valid_obs) >= 4 else valid_obs

        obs_str = ", ".join(f"{o.date}: {o.value}" for o in recent) if recent else "no data"

        lines.append(
            f"- {name} ({series_id}): Latest = {latest_val} as of {latest_date}"
        )
        lines.append(f"  Recent observations: {obs_str}")

        # Add frequency/unit context
        if reg:
            lines.append(f"  Frequency: {reg.frequency}, Unit: {reg.unit_type}, Transform: {reg.default_transform}")
        lines.append("")

    return "\n".join(lines) if lines else "No FRED series data available for this run."


def review_newsletter(
    chart_of_the_day: dict,
    from_the_research: list[dict],
    in_the_data: list[dict],
    headlines: list[dict],
    ground_truth_summary: str,
) -> dict:
    """
    Run the Chief Economist review on the assembled newsletter.

    Makes a single Claude Sonnet call to review all content against
    ground-truth FRED data. Returns the review verdict and any fixes.

    Args:
        chart_of_the_day: COTD section dict.
        from_the_research: Research picks list.
        in_the_data: Data story list.
        headlines: Headlines roundup list.
        ground_truth_summary: Ground truth data string.

    Returns:
        Review result dict with verdict, issues_found, and reviewer_notes.
        On failure, returns a pass-through dict (don't block the newsletter
        on reviewer errors).
    """
    api_key = get_env("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = _build_review_prompt(
        chart_of_the_day,
        from_the_research,
        in_the_data,
        headlines,
        ground_truth_summary,
    )

    try:
        response = client.messages.create(
            model=REVIEWER_MODEL,
            max_tokens=2000,
            system=REVIEW_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        # Parse the review JSON
        result = _extract_review_json(text)
        if result is None:
            logger.warning("Could not parse reviewer response — passing through")
            return {"verdict": "pass", "issues_found": [], "reviewer_notes": "Review parse failed — passed through"}

        return result

    except Exception:
        logger.error("Reviewer call failed — passing through", exc_info=True)
        return {"verdict": "pass", "issues_found": [], "reviewer_notes": "Review call failed — passed through"}


def apply_fixes(
    review: dict,
    chart_of_the_day: dict,
    from_the_research: list[dict],
    in_the_data: list[dict],
    headlines: list[dict],
) -> int:
    """
    Apply critical fixes from the reviewer to the newsletter content.

    Modifies the section dicts in place.

    Args:
        review: The review result dict from review_newsletter().
        chart_of_the_day: COTD section dict (modified in place).
        from_the_research: Research section list (modified in place).
        in_the_data: Data stories list (modified in place).
        headlines: Headlines list (modified in place).

    Returns:
        Number of fixes applied.
    """
    fixes_applied = 0

    for issue in review.get("issues_found", []):
        if issue.get("severity") != "critical":
            continue

        fix_text = issue.get("fix")
        if not fix_text:
            continue

        section = issue.get("section", "")
        field = issue.get("field", "")
        index = issue.get("item_index", 0)

        try:
            if section == "chart_of_the_day" and field in chart_of_the_day:
                old = chart_of_the_day[field]
                chart_of_the_day[field] = fix_text
                logger.info("REVIEW FIX [COTD.%s]: '%s' → '%s'", field, old[:60], fix_text[:60])
                fixes_applied += 1

            elif section == "in_the_data" and 0 <= index < len(in_the_data):
                if field in in_the_data[index]:
                    old = in_the_data[index][field]
                    in_the_data[index][field] = fix_text
                    logger.info("REVIEW FIX [data[%d].%s]: '%s' → '%s'", index, field, str(old)[:60], fix_text[:60])
                    fixes_applied += 1

            elif section == "from_the_research" and 0 <= index < len(from_the_research):
                if field in from_the_research[index]:
                    old = from_the_research[index][field]
                    from_the_research[index][field] = fix_text
                    logger.info("REVIEW FIX [research[%d].%s]: '%s' → '%s'", index, field, str(old)[:60], fix_text[:60])
                    fixes_applied += 1

            elif section == "headlines" and 0 <= index < len(headlines):
                if field in headlines[index]:
                    old = headlines[index][field]
                    headlines[index][field] = fix_text
                    logger.info("REVIEW FIX [headlines[%d].%s]: '%s' → '%s'", index, field, str(old)[:60], fix_text[:60])
                    fixes_applied += 1

        except (IndexError, KeyError, TypeError) as exc:
            logger.warning("Could not apply fix for %s.%s[%d]: %s", section, field, index, exc)
            continue

    return fixes_applied


def _extract_review_json(text: str) -> dict | None:
    """Extract JSON from the reviewer's response text."""
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

    # Balanced bracket extraction
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
