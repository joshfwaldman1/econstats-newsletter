"""
FRED series registry with iron law validation.

Provides lookup functions and enforces charting rules that prevent
misleading visualizations (e.g., mixing quarterly and monthly data,
combining different unit types on the same chart).
"""

from __future__ import annotations

import logging

from config import (
    FRED_REGISTRY,
    INDEX_SERIES_REQUIRE_YOY,
    IRON_LAW_CONFLICTS,
    FredSeries,
)

logger = logging.getLogger(__name__)


def lookup(series_id: str) -> FredSeries | None:
    """
    Look up a FRED series by its ID.

    Args:
        series_id: FRED series identifier (e.g. "UNRATE").

    Returns:
        FredSeries metadata if found, None otherwise.
    """
    return FRED_REGISTRY.get(series_id)


def get_default_transform(series_id: str) -> str:
    """
    Get the default data transformation for a series.

    Index series (CPI, PCE, etc.) default to "pc1" (YoY %).
    Others default to "lin" (levels).

    Args:
        series_id: FRED series identifier.

    Returns:
        Transform code: "lin", "pc1", "pch", "ch1", or "chg".
    """
    series = lookup(series_id)
    if series:
        return series.default_transform
    # Fallback: if it's a known index series, use YoY %
    if series_id in INDEX_SERIES_REQUIRE_YOY:
        return "pc1"
    return "lin"


def requires_yoy_percent(series_id: str) -> bool:
    """
    Check if a series must be displayed as YoY % change.

    Raw index values (e.g., CPI = 326) are meaningless without context.
    These series must always be shown as year-over-year percent change.

    Args:
        series_id: FRED series identifier.

    Returns:
        True if the series must be transformed to YoY %.
    """
    return series_id in INDEX_SERIES_REQUIRE_YOY


def validate_chart_combination(series_ids: list[str]) -> list[str]:
    """
    Validate that a set of series can be safely plotted together.

    Checks:
    1. Iron law conflicts (known incompatible combinations)
    2. Frequency mismatches (quarterly + monthly)
    3. Unit type mismatches (percent + thousands, index + dollars)

    Args:
        series_ids: List of FRED series IDs to combine on one chart.

    Returns:
        List of violation messages. Empty list = safe to combine.
    """
    violations: list[str] = []
    id_set = set(series_ids)

    if len(series_ids) < 2:
        return violations

    # Check explicit iron law conflicts
    for conflict_set, reason in IRON_LAW_CONFLICTS:
        overlap = id_set & conflict_set
        if len(overlap) >= 2:
            violations.append(f"Iron law violation: {reason} (series: {', '.join(sorted(overlap))})")

    # Check frequency mismatches
    frequencies: dict[str, list[str]] = {}
    for sid in series_ids:
        series = lookup(sid)
        if series:
            freq = series.frequency
            frequencies.setdefault(freq, []).append(sid)

    if "quarterly" in frequencies and any(
        f in frequencies for f in ("monthly", "weekly", "daily")
    ):
        quarterly = frequencies["quarterly"]
        others = [
            sid
            for f, sids in frequencies.items()
            if f != "quarterly"
            for sid in sids
        ]
        violations.append(
            f"Frequency mismatch: quarterly series ({', '.join(quarterly)}) "
            f"cannot share a chart with {', '.join(others)}"
        )

    # Check unit type mismatches
    unit_types: dict[str, list[str]] = {}
    for sid in series_ids:
        series = lookup(sid)
        if series:
            ut = series.unit_type
            unit_types.setdefault(ut, []).append(sid)

    if len(unit_types) > 1:
        type_summary = ", ".join(
            f"{ut}: {', '.join(sids)}" for ut, sids in unit_types.items()
        )
        violations.append(
            f"Unit type mismatch: cannot combine different units on same chart ({type_summary})"
        )

    if violations:
        logger.warning(
            "Chart validation failed for %s: %s",
            series_ids,
            "; ".join(violations),
        )

    return violations


def get_series_for_topic(topic: str) -> list[str]:
    """
    Suggest relevant FRED series for a given economic topic.

    Used by the curation layer to map news stories to charts.

    Args:
        topic: Economic topic keyword (e.g. "inflation", "jobs").

    Returns:
        List of suggested FRED series IDs.
    """
    topic_lower = topic.lower()

    topic_map: dict[str, list[str]] = {
        "jobs": ["PAYEMS", "UNRATE", "LNS12300060", "ICSA"],
        "employment": ["PAYEMS", "UNRATE", "LNS12300060", "JTSJOL"],
        "unemployment": ["UNRATE", "U6RATE", "ICSA", "CCSA"],
        "labor": ["LNS12300060", "CIVPART", "JTSJOL", "JTSQUR"],
        "wages": ["CES0500000003"],
        "inflation": ["CPIAUCSL", "CPILFESL", "PCEPILFE"],
        "cpi": ["CPIAUCSL", "CPILFESL"],
        "pce": ["PCEPILFE"],
        "prices": ["CPIAUCSL", "CPILFESL", "CPIUFDSL", "CPIENGSL"],
        "food": ["CPIUFDSL"],
        "energy": ["CPIENGSL"],
        "housing": ["CSUSHPINSA", "HOUST", "PERMIT", "MORTGAGE30US"],
        "mortgage": ["MORTGAGE30US"],
        "rent": ["CUSR0000SAH1"],
        "gdp": ["GDPC1", "A191RL1Q225SBEA"],
        "growth": ["GDPC1", "A191RL1Q225SBEA"],
        "recession": ["GDPC1", "UNRATE", "T10Y2Y", "ICSA"],
        "fed": ["FEDFUNDS", "DGS2", "DGS10"],
        "rates": ["FEDFUNDS", "DGS10", "DGS2", "MORTGAGE30US"],
        "treasury": ["DGS10", "DGS2", "T10Y2Y"],
        "yield curve": ["T10Y2Y"],
        "consumer": ["UMCSENT", "RSXFS", "PSAVERT"],
        "sentiment": ["UMCSENT"],
        "retail": ["RSXFS"],
        "savings": ["PSAVERT"],
        "financial": ["NFCI", "BAA10Y"],
        "credit": ["BAA10Y"],
        "manufacturing": ["MANEMP"],
        "construction": ["USCONS"],
    }

    for keyword, series_list in topic_map.items():
        if keyword in topic_lower:
            return series_list

    # Default: broad macro indicators
    return ["UNRATE", "CPIAUCSL", "FEDFUNDS", "GDPC1"]


def get_registry_summary() -> str:
    """
    Generate a compact text summary of the FRED registry for Claude prompts.

    Returns:
        Multi-line string listing all series with key metadata.
    """
    lines: list[str] = ["Available FRED series:"]
    current_category = ""

    # Group by category
    by_category: dict[str, list[FredSeries]] = {}
    for series in FRED_REGISTRY.values():
        by_category.setdefault(series.category, []).append(series)

    for category, series_list in by_category.items():
        lines.append(f"\n  {category.upper()}:")
        for s in series_list:
            transform_note = f" [show as YoY%]" if s.series_id in INDEX_SERIES_REQUIRE_YOY else ""
            lines.append(f"    {s.series_id}: {s.name} ({s.frequency}, {s.unit_type}){transform_note}")
            if s.notes:
                lines.append(f"      Note: {s.notes}")

    return "\n".join(lines)
