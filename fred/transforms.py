"""
Data transformations and formatting for FRED series.

Handles YoY% calculation (date-based, not position-based),
value formatting for display, and unit-aware labeling.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fred.client import Observation

logger = logging.getLogger(__name__)


def compute_yoy_percent(observations: list[Observation]) -> list[Observation]:
    """
    Compute year-over-year percent change from raw levels.

    Uses date-based matching (not position-based values[i-12]) to handle
    gaps and irregular spacing correctly.

    Args:
        observations: Chronologically sorted list of raw-level observations.

    Returns:
        New list of Observation with YoY % values. Observations without
        a year-ago match are excluded.
    """
    # Build a date→value lookup for fast year-ago matching
    date_lookup: dict[str, float] = {}
    for obs in observations:
        if obs.value is not None:
            date_lookup[obs.date] = obs.value

    result: list[Observation] = []
    for obs in observations:
        if obs.value is None:
            continue

        # Find the corresponding date one year earlier
        try:
            current_date = datetime.strptime(obs.date, "%Y-%m-%d")
            year_ago_date = current_date.replace(year=current_date.year - 1)
            year_ago_key = year_ago_date.strftime("%Y-%m-%d")
        except ValueError:
            # Handle Feb 29 → Feb 28 edge case
            try:
                current_date = datetime.strptime(obs.date, "%Y-%m-%d")
                year_ago_date = current_date.replace(
                    year=current_date.year - 1, day=28
                )
                year_ago_key = year_ago_date.strftime("%Y-%m-%d")
            except ValueError:
                continue

        year_ago_value = date_lookup.get(year_ago_key)
        if year_ago_value is not None and year_ago_value != 0:
            yoy_pct = ((obs.value - year_ago_value) / year_ago_value) * 100
            result.append(Observation(date=obs.date, value=round(yoy_pct, 2)))

    logger.debug("YoY%% transform: %d → %d observations", len(observations), len(result))
    return result


def format_value(value: float | None, unit_type: str, transform: str = "lin") -> str:
    """
    Format a numeric value for display with appropriate units.

    Args:
        value: The numeric value to format. None returns "N/A".
        unit_type: The series unit type (percent, thousands, index, etc.).
        transform: The applied transform (lin, pc1, pch, etc.).

    Returns:
        Formatted string (e.g., "3.7%", "158,000", "$34.25").
    """
    if value is None:
        return "N/A"

    # YoY% and other percent-change transforms
    if transform in ("pc1", "pch"):
        return f"{value:+.1f}%"

    # Change transforms
    if transform in ("ch1", "chg"):
        if unit_type == "thousands":
            return f"{value:+,.0f}K"
        return f"{value:+,.1f}"

    # Level transforms by unit type
    if unit_type == "percent":
        return f"{value:.1f}%"
    elif unit_type == "thousands":
        return f"{value:,.0f}K"
    elif unit_type == "millions":
        return f"${value:,.0f}M"
    elif unit_type == "billions":
        return f"${value:,.1f}B"
    elif unit_type == "dollars":
        return f"${value:.2f}"
    elif unit_type == "index":
        return f"{value:.1f}"
    elif unit_type == "ratio":
        return f"{value:.2f}"
    else:
        return f"{value:,.1f}"


def get_latest_value(observations: list[Observation]) -> Observation | None:
    """
    Get the most recent non-null observation.

    Args:
        observations: Chronologically sorted list of observations.

    Returns:
        The latest Observation with a non-null value, or None.
    """
    for obs in reversed(observations):
        if obs.value is not None:
            return obs
    return None


def get_change_summary(
    observations: list[Observation],
    unit_type: str,
    transform: str = "lin",
) -> str:
    """
    Generate a brief text summary of the latest value and its change.

    Example: "3.7% (↓0.1pp from prior month)"

    Args:
        observations: Chronologically sorted observations.
        unit_type: Series unit type for formatting.
        transform: Applied data transform.

    Returns:
        Summary string, or "No data available" if insufficient data.
    """
    valid = [obs for obs in observations if obs.value is not None]
    if not valid:
        return "No data available"

    latest = valid[-1]
    formatted_latest = format_value(latest.value, unit_type, transform)

    if len(valid) >= 2:
        prior = valid[-2]
        if prior.value is not None and latest.value is not None:
            change = latest.value - prior.value
            direction = "↑" if change > 0 else "↓" if change < 0 else "→"
            abs_change = abs(change)

            if unit_type == "percent" or transform in ("pc1", "pch"):
                change_str = f"{direction}{abs_change:.1f}pp"
            elif unit_type == "thousands":
                change_str = f"{direction}{abs_change:,.0f}K"
            else:
                change_str = f"{direction}{abs_change:,.1f}"

            return f"{formatted_latest} ({change_str} from prior period)"

    return formatted_latest


def build_alt_text(
    series_id: str,
    title: str,
    observations: list[Observation],
    unit_type: str,
    transform: str,
) -> str:
    """
    Build data-rich alt text for chart images.

    Critical for email clients that block images — the alt text should
    convey the key data point even without the chart visible.

    Args:
        series_id: FRED series ID.
        title: Human-readable series title.
        observations: The plotted observations.
        unit_type: Series unit type.
        transform: Applied transform.

    Returns:
        Alt text string with latest value and trend context.
    """
    latest = get_latest_value(observations)
    if latest is None:
        return f"Chart: {title} ({series_id}) — no recent data"

    formatted = format_value(latest.value, unit_type, transform)
    change_summary = get_change_summary(observations, unit_type, transform)

    return f"Chart: {title} — Latest: {change_summary} (as of {latest.date}). Source: FRED/{series_id}"
