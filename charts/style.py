"""
Shared matplotlib chart styling for the EconStats newsletter.

Provides a consistent, professional look across all FRED charts.
Designed for email rendering: clean, readable at 600px width,
optimized file size (<200KB per chart PNG).
"""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from config import (
    CHART_BG_COLOR,
    CHART_COLORS,
    CHART_DPI,
    CHART_FONT_FAMILY,
    CHART_GRID_COLOR,
    CHART_HEIGHT_PX,
    CHART_TEXT_COLOR,
    CHART_WIDTH_PX,
)

# Use non-interactive backend for headless / CI environments
matplotlib.use("Agg")


def apply_newsletter_style() -> None:
    """
    Apply the EconStats newsletter matplotlib style globally.

    Call this once at startup before rendering any charts.
    Sets font, colors, grid, and layout defaults.
    """
    plt.rcParams.update({
        # Font
        "font.family": "serif",
        "font.serif": [CHART_FONT_FAMILY, "Times New Roman", "DejaVu Serif"],
        "font.size": 10,

        # Colors
        "text.color": CHART_TEXT_COLOR,
        "axes.labelcolor": CHART_TEXT_COLOR,
        "xtick.color": CHART_TEXT_COLOR,
        "ytick.color": CHART_TEXT_COLOR,

        # Background
        "figure.facecolor": CHART_BG_COLOR,
        "axes.facecolor": CHART_BG_COLOR,

        # Grid
        "axes.grid": True,
        "grid.color": CHART_GRID_COLOR,
        "grid.linewidth": 0.5,
        "grid.alpha": 0.7,

        # Axes
        "axes.linewidth": 0.8,
        "axes.edgecolor": "#CCCCCC",
        "axes.spines.top": False,
        "axes.spines.right": False,

        # Ticks
        "xtick.major.size": 4,
        "ytick.major.size": 4,
        "xtick.direction": "out",
        "ytick.direction": "out",

        # Legend
        "legend.frameon": False,
        "legend.fontsize": 9,

        # Layout
        "figure.dpi": CHART_DPI,
        "savefig.dpi": CHART_DPI,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.15,
    })


def create_figure() -> tuple[Figure, plt.Axes]:
    """
    Create a new figure with the standard newsletter dimensions.

    Returns:
        Tuple of (Figure, Axes) configured for email-width charts.
    """
    fig_width = CHART_WIDTH_PX / CHART_DPI
    fig_height = CHART_HEIGHT_PX / CHART_DPI

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    return fig, ax


def get_color(index: int = 0) -> str:
    """
    Get a color from the newsletter palette.

    Args:
        index: Color index (wraps around if > palette size).

    Returns:
        Hex color string.
    """
    return CHART_COLORS[index % len(CHART_COLORS)]


def format_source_label(series_id: str) -> str:
    """
    Generate a source attribution label for chart footer.

    Uses the source_agency field from the registry when available,
    falling back to prefix-based heuristics. Always attributes the
    actual data agency, not "FRED" (which is just the distribution platform).

    Args:
        series_id: FRED series identifier.

    Returns:
        Attribution string like "Source: U.S. Bureau of Labor Statistics | EconStats".
    """
    from fred.registry import lookup

    # Use registry source_agency if available
    entry = lookup(series_id)
    if entry and entry.source_agency:
        return f"Source: {entry.source_agency} | EconStats"

    # Fallback: prefix-based heuristics
    bls_prefixes = ("LNS", "CES", "UNRATE", "CIVPART", "U6RATE", "CPI", "CUSR", "JTS")
    if any(series_id.startswith(p) for p in bls_prefixes):
        return f"Source: U.S. Bureau of Labor Statistics | EconStats"

    bea_prefixes = ("GDP", "A191", "PCE", "PSAVERT")
    if any(series_id.startswith(p) for p in bea_prefixes):
        return f"Source: U.S. Bureau of Economic Analysis | EconStats"

    fed_prefixes = ("DGS", "T10Y", "FEDFUNDS", "NFCI", "BAA")
    if any(series_id.startswith(p) for p in fed_prefixes):
        return f"Source: Federal Reserve | EconStats"

    return f"Source: FRED ({series_id}) | EconStats"
