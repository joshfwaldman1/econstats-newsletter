"""
FRED time-series chart renderer using matplotlib.

Produces clean, email-ready PNG charts from FRED observations.
Handles date formatting, axis labeling, recession shading context,
and outputs optimized file sizes (<200KB).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from charts.style import create_figure, format_source_label, get_color
from config import CHART_DPI, CHART_MAX_SIZE_KB
from fred.client import Observation, SeriesData
from fred.registry import lookup, requires_yoy_percent
from fred.transforms import build_alt_text, format_value, get_latest_value

logger = logging.getLogger(__name__)


def render_chart(
    series_data: SeriesData,
    *,
    output_dir: str | Path = "output/charts",
    title_override: str | None = None,
    highlight_latest: bool = True,
    show_source: bool = True,
    color_index: int = 0,
) -> dict[str, str]:
    """
    Render a single FRED series as a PNG chart.

    Args:
        series_data: SeriesData from fred.client.fetch_series().
        output_dir: Directory to write the PNG file.
        title_override: Custom chart title (defaults to series title).
        highlight_latest: Whether to mark the most recent data point.
        show_source: Whether to show source attribution below chart.
        color_index: Index into the chart color palette.

    Returns:
        Dict with keys:
            - "path": absolute path to the PNG file
            - "alt_text": data-rich alt text for the image
            - "series_id": the FRED series ID
            - "latest_value": formatted latest value string
            - "latest_date": date of latest observation
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Filter out null values for plotting
    valid_obs = [obs for obs in series_data.observations if obs.value is not None]
    if not valid_obs:
        logger.warning("No valid observations for %s — skipping chart", series_data.series_id)
        return {}

    # Parse dates and values
    dates = [datetime.strptime(obs.date, "%Y-%m-%d") for obs in valid_obs]
    values = [obs.value for obs in valid_obs]

    # Determine transform info from registry
    registry_entry = lookup(series_data.series_id)
    unit_type = registry_entry.unit_type if registry_entry else "index"
    transform = registry_entry.default_transform if registry_entry else "lin"

    # Create figure
    fig, ax = create_figure()
    line_color = get_color(color_index)

    # Plot the line
    ax.plot(
        dates,
        values,
        color=line_color,
        linewidth=1.8,
        solid_capstyle="round",
    )

    # Light fill under the line
    ax.fill_between(
        dates,
        values,
        alpha=0.08,
        color=line_color,
    )

    # Highlight the latest data point
    if highlight_latest and valid_obs:
        latest = valid_obs[-1]
        latest_date = dates[-1]
        ax.plot(
            latest_date,
            latest.value,
            "o",
            color=line_color,
            markersize=5,
            zorder=5,
        )
        # Annotate with the value
        formatted = format_value(latest.value, unit_type, transform)
        ax.annotate(
            formatted,
            (latest_date, latest.value),
            textcoords="offset points",
            xytext=(8, 8),
            fontsize=9,
            fontweight="bold",
            color=line_color,
        )

    # Title
    chart_title = title_override or series_data.title
    if requires_yoy_percent(series_data.series_id) and "%" not in chart_title.lower() and "change" not in chart_title.lower():
        chart_title += " (YoY % Change)"
    ax.set_title(chart_title, fontsize=12, fontweight="bold", pad=10)

    # Y-axis label
    ax.set_ylabel(series_data.units, fontsize=9, color="#666666")

    # X-axis date formatting
    _auto_format_dates(ax, dates)

    # Y-axis formatting
    _auto_format_yaxis(ax, values, unit_type, transform)

    # Source attribution
    if show_source:
        source_text = format_source_label(series_data.series_id)
        fig.text(
            0.99, 0.01,
            source_text,
            fontsize=7,
            color="#999999",
            ha="right",
            va="bottom",
            transform=fig.transFigure,
        )

    # Save
    filename = f"{series_data.series_id.lower()}_{datetime.now().strftime('%Y%m%d')}.png"
    filepath = output_path / filename

    fig.savefig(
        filepath,
        dpi=CHART_DPI,
        bbox_inches="tight",
        pad_inches=0.15,
        facecolor="white",
        edgecolor="none",
    )
    plt.close(fig)

    # Check file size
    file_size_kb = filepath.stat().st_size / 1024
    if file_size_kb > CHART_MAX_SIZE_KB:
        logger.warning(
            "Chart %s is %.0fKB (exceeds %dKB target)",
            filename,
            file_size_kb,
            CHART_MAX_SIZE_KB,
        )

    # Build alt text
    latest_obs = get_latest_value(valid_obs)
    alt_text = build_alt_text(
        series_data.series_id,
        chart_title,
        valid_obs,
        unit_type,
        transform,
    )

    logger.info("Rendered chart: %s (%.0fKB)", filename, file_size_kb)

    return {
        "path": str(filepath.resolve()),
        "alt_text": alt_text,
        "series_id": series_data.series_id,
        "latest_value": format_value(latest_obs.value, unit_type, transform) if latest_obs else "N/A",
        "latest_date": latest_obs.date if latest_obs else "",
    }


def _auto_format_dates(ax: plt.Axes, dates: list[datetime]) -> None:
    """
    Automatically set date axis formatting based on the time span.

    Short spans (<2 years): monthly labels.
    Medium spans (2-10 years): yearly labels.
    Long spans (>10 years): every-other-year labels.
    """
    if not dates:
        return

    span_days = (dates[-1] - dates[0]).days

    if span_days < 365 * 2:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    elif span_days < 365 * 10:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    else:
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)


def _auto_format_yaxis(
    ax: plt.Axes,
    values: list[float],
    unit_type: str,
    transform: str,
) -> None:
    """
    Format the Y-axis based on data type and range.

    Adds percent signs, thousands separators, etc.
    """
    if unit_type == "percent" or transform in ("pc1", "pch"):
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    elif unit_type == "thousands":
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
        )
    elif unit_type == "dollars":
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"${x:.2f}")
        )
    elif unit_type in ("millions", "billions"):
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

    # Add zero line if data crosses zero
    if values and min(values) < 0 < max(values):
        ax.axhline(y=0, color="#999999", linewidth=0.5, linestyle="-")
