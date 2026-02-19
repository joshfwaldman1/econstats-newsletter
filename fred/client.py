"""
FRED API client for fetching economic time-series data.

Handles authentication, observation fetching, and basic error handling.
Uses the FRED REST API (https://fred.stlouisfed.org/docs/api/fred/).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests

from config import FRED_API_BASE_URL, FRED_DEFAULT_OBSERVATION_LIMIT, get_env

logger = logging.getLogger(__name__)


@dataclass
class Observation:
    """A single FRED data point."""

    date: str       # ISO date string, e.g. "2024-01-01"
    value: float | None  # None for missing (".") values


@dataclass
class SeriesData:
    """Complete response for a FRED series fetch."""

    series_id: str
    title: str
    units: str
    frequency: str
    observations: list[Observation]


def fetch_series(
    series_id: str,
    *,
    units: str = "lin",
    limit: int | None = None,
    observation_start: str | None = None,
    observation_end: str | None = None,
) -> SeriesData:
    """
    Fetch observations for a FRED series.

    Args:
        series_id: FRED series identifier (e.g. "UNRATE").
        units: Transformation to apply:
            - "lin"  = levels (no transform)
            - "pc1"  = year-over-year percent change
            - "pch"  = period-over-period percent change
            - "ch1"  = year-over-year change
            - "chg"  = period-over-period change
        limit: Max observations to return. Defaults to config value.
        observation_start: Start date (ISO format). Defaults to ~10 years ago.
        observation_end: End date (ISO format). Defaults to today.

    Returns:
        SeriesData with title, units, and list of observations.

    Raises:
        requests.HTTPError: On API errors.
        ValueError: If series not found.
    """
    api_key = get_env("FRED_API_KEY")
    effective_limit = limit or FRED_DEFAULT_OBSERVATION_LIMIT

    # Default start date: 10 years back for monthly, 5 for daily
    if observation_start is None:
        observation_start = (datetime.now() - timedelta(days=3650)).strftime("%Y-%m-%d")
    if observation_end is None:
        observation_end = datetime.now().strftime("%Y-%m-%d")

    # Step 1: Fetch series metadata for title + units
    meta_params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    meta_resp = requests.get(
        f"{FRED_API_BASE_URL}/series",
        params=meta_params,
        timeout=15,
    )
    meta_resp.raise_for_status()
    meta_data = meta_resp.json()

    if "seriess" not in meta_data or not meta_data["seriess"]:
        raise ValueError(f"FRED series not found: {series_id}")

    series_info = meta_data["seriess"][0]
    title = series_info.get("title", series_id)
    raw_units = series_info.get("units", "")
    frequency = series_info.get("frequency", "")

    # Step 2: Fetch observations
    obs_params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "units": units,
        "sort_order": "desc",
        "limit": effective_limit,
        "observation_start": observation_start,
        "observation_end": observation_end,
    }
    obs_resp = requests.get(
        f"{FRED_API_BASE_URL}/series/observations",
        params=obs_params,
        timeout=15,
    )
    obs_resp.raise_for_status()
    obs_data = obs_resp.json()

    # Parse observations, handling missing values
    observations: list[Observation] = []
    for obs in obs_data.get("observations", []):
        raw_value = obs.get("value", ".")
        if raw_value == "." or raw_value is None:
            value = None
        else:
            try:
                value = float(raw_value)
            except (ValueError, TypeError):
                value = None
        observations.append(Observation(date=obs["date"], value=value))

    # Reverse to chronological order (API returns desc)
    observations.reverse()

    # Adjust units label if transformation was applied
    units_label = raw_units
    if units == "pc1":
        units_label = "Year-over-Year % Change"
    elif units == "pch":
        units_label = "% Change from Prior Period"
    elif units == "ch1":
        units_label = "Year-over-Year Change"
    elif units == "chg":
        units_label = "Change from Prior Period"

    logger.info(
        "Fetched %d observations for %s (%s)",
        len(observations),
        series_id,
        units_label,
    )

    return SeriesData(
        series_id=series_id,
        title=title,
        units=units_label,
        frequency=frequency,
        observations=observations,
    )
