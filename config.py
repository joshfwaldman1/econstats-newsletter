"""
Configuration for the EconStats Daily Newsletter.

Contains FRED series registry, news sources, email settings,
chart styling constants, and iron law validation rules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# FRED Series Registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FredSeries:
    """Metadata for a single FRED series."""

    series_id: str
    name: str
    category: str
    frequency: str          # "monthly", "quarterly", "weekly", "daily"
    unit_type: str          # "percent", "thousands", "index", "dollars", "ratio", "billions"
    default_transform: str  # "lin" (levels), "pc1" (YoY%), "pch" (period%), "ch1" (YoY change)
    description: str = ""
    notes: str = ""         # Domain-specific caveats


# Full curated registry — ported from EconStats Agent + V2
FRED_REGISTRY: dict[str, FredSeries] = {
    # ── Employment (Payroll / CES) ─────────────────────────────────────
    "PAYEMS": FredSeries(
        series_id="PAYEMS",
        name="Total Nonfarm Payrolls",
        category="employment",
        frequency="monthly",
        unit_type="thousands",
        default_transform="ch1",
        description="Headline jobs number from BLS establishment survey",
    ),
    "CES0500000003": FredSeries(
        series_id="CES0500000003",
        name="Average Hourly Earnings (Private)",
        category="wages",
        frequency="monthly",
        unit_type="dollars",
        default_transform="pc1",
        description="Average hourly earnings, all private employees",
        notes="Show YoY% for trend analysis; nominal, not real",
    ),
    "MANEMP": FredSeries(
        series_id="MANEMP",
        name="Manufacturing Employment",
        category="employment",
        frequency="monthly",
        unit_type="thousands",
        default_transform="lin",
    ),
    "USCONS": FredSeries(
        series_id="USCONS",
        name="Construction Employment",
        category="employment",
        frequency="monthly",
        unit_type="thousands",
        default_transform="lin",
    ),

    # ── Employment (Household / CPS) ───────────────────────────────────
    "UNRATE": FredSeries(
        series_id="UNRATE",
        name="Unemployment Rate (U-3)",
        category="employment",
        frequency="monthly",
        unit_type="percent",
        default_transform="lin",
        description="Headline unemployment rate from household survey",
    ),
    "CIVPART": FredSeries(
        series_id="CIVPART",
        name="Labor Force Participation Rate",
        category="employment",
        frequency="monthly",
        unit_type="percent",
        default_transform="lin",
        description="Share of 16+ population in labor force",
    ),
    "LNS12300060": FredSeries(
        series_id="LNS12300060",
        name="Prime-Age Employment-Population Ratio",
        category="employment",
        frequency="monthly",
        unit_type="percent",
        default_transform="lin",
        description="Best single measure of labor market tightness (25-54)",
        notes="Preferred over overall LFPR — controls for Boomer retirement",
    ),
    "JTSJOL": FredSeries(
        series_id="JTSJOL",
        name="Job Openings (JOLTS)",
        category="employment",
        frequency="monthly",
        unit_type="thousands",
        default_transform="lin",
    ),
    "JTSQUR": FredSeries(
        series_id="JTSQUR",
        name="Quits Rate (JOLTS)",
        category="employment",
        frequency="monthly",
        unit_type="percent",
        default_transform="lin",
    ),
    "U6RATE": FredSeries(
        series_id="U6RATE",
        name="U-6 Unemployment Rate",
        category="employment",
        frequency="monthly",
        unit_type="percent",
        default_transform="lin",
        description="Broadest unemployment measure — includes discouraged + part-time for economic reasons",
    ),
    "ICSA": FredSeries(
        series_id="ICSA",
        name="Initial Jobless Claims",
        category="employment",
        frequency="weekly",
        unit_type="thousands",
        default_transform="lin",
        description="Best real-time labor market signal",
    ),
    "CCSA": FredSeries(
        series_id="CCSA",
        name="Continued Jobless Claims",
        category="employment",
        frequency="weekly",
        unit_type="thousands",
        default_transform="lin",
    ),

    # ── Demographic Unemployment ───────────────────────────────────────
    "LNS14000006": FredSeries(
        series_id="LNS14000006",
        name="Black Unemployment Rate",
        category="employment",
        frequency="monthly",
        unit_type="percent",
        default_transform="lin",
    ),
    "LNS14000009": FredSeries(
        series_id="LNS14000009",
        name="Hispanic Unemployment Rate",
        category="employment",
        frequency="monthly",
        unit_type="percent",
        default_transform="lin",
    ),

    # ── Inflation ──────────────────────────────────────────────────────
    "CPIAUCSL": FredSeries(
        series_id="CPIAUCSL",
        name="CPI (All Items)",
        category="inflation",
        frequency="monthly",
        unit_type="index",
        default_transform="pc1",
        description="Headline consumer price index",
        notes="ALWAYS show as YoY % — raw index value is meaningless",
    ),
    "CPILFESL": FredSeries(
        series_id="CPILFESL",
        name="Core CPI (Less Food & Energy)",
        category="inflation",
        frequency="monthly",
        unit_type="index",
        default_transform="pc1",
        description="CPI excluding volatile food and energy",
        notes="ALWAYS show as YoY % — raw index value is meaningless",
    ),
    "PCEPILFE": FredSeries(
        series_id="PCEPILFE",
        name="Core PCE Price Index",
        category="inflation",
        frequency="monthly",
        unit_type="index",
        default_transform="pc1",
        description="Fed's preferred inflation target measure",
        notes="ALWAYS show as YoY % — raw index value is meaningless",
    ),
    "CPIUFDSL": FredSeries(
        series_id="CPIUFDSL",
        name="Food CPI",
        category="inflation",
        frequency="monthly",
        unit_type="index",
        default_transform="pc1",
        notes="Show as YoY %",
    ),
    "CPIENGSL": FredSeries(
        series_id="CPIENGSL",
        name="Energy CPI",
        category="inflation",
        frequency="monthly",
        unit_type="index",
        default_transform="pc1",
        notes="Show as YoY %",
    ),
    "CUSR0000SAH1": FredSeries(
        series_id="CUSR0000SAH1",
        name="Shelter CPI",
        category="inflation",
        frequency="monthly",
        unit_type="index",
        default_transform="pc1",
        notes="Lags actual market rents by ~12 months",
    ),

    # ── Growth ─────────────────────────────────────────────────────────
    "GDPC1": FredSeries(
        series_id="GDPC1",
        name="Real GDP",
        category="growth",
        frequency="quarterly",
        unit_type="billions",
        default_transform="pc1",
        description="Real (inflation-adjusted) GDP — ALWAYS use this, never nominal",
    ),
    "A191RL1Q225SBEA": FredSeries(
        series_id="A191RL1Q225SBEA",
        name="Real GDP Growth Rate (SAAR)",
        category="growth",
        frequency="quarterly",
        unit_type="percent",
        default_transform="lin",
        description="Annualized quarterly GDP growth rate",
    ),

    # ── Interest Rates ─────────────────────────────────────────────────
    "FEDFUNDS": FredSeries(
        series_id="FEDFUNDS",
        name="Federal Funds Rate",
        category="rates",
        frequency="monthly",
        unit_type="percent",
        default_transform="lin",
    ),
    "DGS10": FredSeries(
        series_id="DGS10",
        name="10-Year Treasury Yield",
        category="rates",
        frequency="daily",
        unit_type="percent",
        default_transform="lin",
    ),
    "DGS2": FredSeries(
        series_id="DGS2",
        name="2-Year Treasury Yield",
        category="rates",
        frequency="daily",
        unit_type="percent",
        default_transform="lin",
    ),
    "T10Y2Y": FredSeries(
        series_id="T10Y2Y",
        name="Yield Curve (10Y minus 2Y)",
        category="rates",
        frequency="daily",
        unit_type="percent",
        default_transform="lin",
        description="Negative = inverted curve, historically precedes recessions",
    ),
    "MORTGAGE30US": FredSeries(
        series_id="MORTGAGE30US",
        name="30-Year Fixed Mortgage Rate",
        category="rates",
        frequency="weekly",
        unit_type="percent",
        default_transform="lin",
    ),

    # ── Housing ────────────────────────────────────────────────────────
    "CSUSHPINSA": FredSeries(
        series_id="CSUSHPINSA",
        name="Case-Shiller Home Price Index",
        category="housing",
        frequency="monthly",
        unit_type="index",
        default_transform="pc1",
        notes="Show as YoY %",
    ),
    "HOUST": FredSeries(
        series_id="HOUST",
        name="Housing Starts",
        category="housing",
        frequency="monthly",
        unit_type="thousands",
        default_transform="lin",
    ),
    "PERMIT": FredSeries(
        series_id="PERMIT",
        name="Building Permits",
        category="housing",
        frequency="monthly",
        unit_type="thousands",
        default_transform="lin",
    ),

    # ── Consumer ───────────────────────────────────────────────────────
    "UMCSENT": FredSeries(
        series_id="UMCSENT",
        name="Consumer Sentiment (UMich)",
        category="consumer",
        frequency="monthly",
        unit_type="index",
        default_transform="lin",
        description="University of Michigan consumer sentiment index",
    ),
    "RSXFS": FredSeries(
        series_id="RSXFS",
        name="Retail Sales (ex. Food Services)",
        category="consumer",
        frequency="monthly",
        unit_type="millions",
        default_transform="pc1",
    ),
    "PSAVERT": FredSeries(
        series_id="PSAVERT",
        name="Personal Savings Rate",
        category="consumer",
        frequency="monthly",
        unit_type="percent",
        default_transform="lin",
    ),

    # ── Financial Conditions ───────────────────────────────────────────
    "NFCI": FredSeries(
        series_id="NFCI",
        name="Chicago Fed NFCI",
        category="financial",
        frequency="weekly",
        unit_type="index",
        default_transform="lin",
        description="Negative = loose conditions, positive = tight",
    ),
    "BAA10Y": FredSeries(
        series_id="BAA10Y",
        name="Corporate Bond Spread (BAA minus 10Y)",
        category="financial",
        frequency="daily",
        unit_type="percent",
        default_transform="lin",
        description="Credit spread — widens during stress",
    ),
}


# ---------------------------------------------------------------------------
# Iron Law Validation — series that must NEVER share a chart
# ---------------------------------------------------------------------------

# Groups of series that cannot be combined on one chart.
# Each tuple is (set_of_series_ids, reason).
IRON_LAW_CONFLICTS: list[tuple[set[str], str]] = [
    # 1. Different frequencies — quarterly vs monthly
    (
        {"GDPC1", "A191RL1Q225SBEA"},  # quarterly
        "Cannot combine quarterly GDP with monthly series — different frequencies",
    ),
    # 2. Different concepts — unemployment vs participation vs EPOP
    (
        {"UNRATE", "CIVPART", "LNS12300060"},
        "Unemployment rate, LFPR, and EPOP measure different concepts",
    ),
    # 3. Prime-age vs all-ages
    (
        {"LNS12300060", "CIVPART"},
        "Prime-age (25-54) vs all-ages (16+) populations are not comparable",
    ),
    # 4. Index vs percent — never combine different unit types
    # (Enforced dynamically in registry.validate_chart_combination)
]

# Series whose raw index values are meaningless — must show as YoY %
INDEX_SERIES_REQUIRE_YOY: set[str] = {
    "CPIAUCSL", "CPILFESL", "PCEPILFE",
    "CPIUFDSL", "CPIENGSL", "CUSR0000SAH1",
    "CSUSHPINSA",
}


# ---------------------------------------------------------------------------
# News Sources
# ---------------------------------------------------------------------------

NEWSAPI_QUERIES: list[dict[str, str]] = [
    {
        "name": "AI",
        "query": '"artificial intelligence" OR "AI" OR "machine learning"',
    },
    {
        "name": "Trade",
        "query": '"tariff" OR "trade war" OR "sanctions" OR "import tax"',
    },
    {
        "name": "Macro",
        "query": '"Federal Reserve" OR "GDP" OR "inflation" OR "unemployment" OR "interest rate"',
    },
    {
        "name": "Policy",
        "query": '"economic policy" OR "fiscal" OR "treasury" OR "NEC"',
    },
    {
        "name": "Tech-Econ",
        "query": '"tech regulation" OR "antitrust" OR "crypto regulation"',
    },
]

RSS_FEEDS: list[dict[str, str]] = [
    # Premium
    {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/economics/news.rss"},
    {"name": "FT", "url": "https://www.ft.com/rss/home/us"},
    {"name": "WSJ", "url": "https://feeds.a]wsj.com/wsj/xml/rss/3_7085.xml"},
    {"name": "NYT", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml"},
    {"name": "Reuters", "url": "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best"},
    {"name": "Politico", "url": "https://rss.politico.com/economy.xml"},
    {"name": "Axios", "url": "https://api.axios.com/feed/"},
    {"name": "The Hill", "url": "https://thehill.com/feed/"},
    # Research
    {"name": "Brookings", "url": "https://www.brookings.edu/feed/"},
    {"name": "NBER", "url": "https://www.nber.org/rss/new.xml"},
    {"name": "VoxEU", "url": "https://cepr.org/rss/columns/feed"},
    {"name": "IMF", "url": "https://www.imf.org/en/News/rss"},
    {"name": "Peterson (PIIE)", "url": "https://www.piie.com/rss.xml"},
    {"name": "FEDS Notes", "url": "https://www.federalreserve.gov/feeds/feds_notes.xml"},
    {"name": "AEI", "url": "https://www.aei.org/feed/"},
    {"name": "CATO", "url": "https://www.cato.org/rss/recent-opeds"},
    # Data
    {"name": "FRED Blog", "url": "https://fredblog.stlouisfed.org/feed/"},
]

# NBER working papers RSS (separate from general NBER feed)
NBER_PAPERS_RSS: str = "https://www.nber.org/rss/new.xml"


# ---------------------------------------------------------------------------
# Email Settings
# ---------------------------------------------------------------------------

SMTP_SERVER: str = "smtp.gmail.com"
SMTP_PORT: int = 587
EMAIL_SUBJECT_PREFIX: str = "EconStats Daily"
EMAIL_RECIPIENT: str = "joshfwaldman@gmail.com"

# Deduplication
FUZZY_MATCH_THRESHOLD: float = 0.85

# Source priority for deduplication — higher = kept when duplicate found
SOURCE_PRIORITY: dict[str, int] = {
    "FT": 10,
    "Bloomberg": 10,
    "WSJ": 9,
    "NYT": 9,
    "Reuters": 8,
    "Economist": 8,
    "Brookings": 8,
    "NBER": 8,
    "Politico": 7,
    "Axios": 7,
    "The Hill": 6,
    "WaPo": 6,
    "VoxEU": 7,
    "IMF": 7,
    "PIIE": 7,
    "AEI": 6,
    "CATO": 6,
    "FRED Blog": 5,
}

# Claude model for curation + annotations
CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"

# Newsletter sections
NEWSLETTER_SECTIONS: list[str] = [
    "Chart of the Day",
    "From the Research",
    "In the Data",
    "Headlines",
]

# Categories for headline-only section
HEADLINE_CATEGORIES: list[str] = [
    "AI",
    "Tariffs/International",
    "Other Econ",
    "Research & Papers",
    "Non-Econ",
]


# ---------------------------------------------------------------------------
# Chart Styling
# ---------------------------------------------------------------------------

CHART_WIDTH_PX: int = 600
CHART_HEIGHT_PX: int = 350
CHART_DPI: int = 150
CHART_MAX_SIZE_KB: int = 200

# Color palette — muted professional tones
CHART_COLORS: list[str] = [
    "#2166AC",  # primary blue
    "#B2182B",  # red
    "#1B7837",  # green
    "#762A83",  # purple
    "#E08214",  # orange
]

CHART_BG_COLOR: str = "#FFFFFF"
CHART_GRID_COLOR: str = "#E5E5E5"
CHART_TEXT_COLOR: str = "#333333"
CHART_FONT_FAMILY: str = "Georgia"


# ---------------------------------------------------------------------------
# GitHub Pages Deployment
# ---------------------------------------------------------------------------

GITHUB_PAGES_REPO: str = "joshfwaldman1/econstats-newsletter"
GITHUB_PAGES_BRANCH: str = "gh-pages"
GITHUB_PAGES_BASE_URL: str = "https://joshfwaldman1.github.io/econstats-newsletter"


# ---------------------------------------------------------------------------
# FRED API
# ---------------------------------------------------------------------------

FRED_API_BASE_URL: str = "https://api.stlouisfed.org/fred"
FRED_DEFAULT_OBSERVATION_LIMIT: int = 120  # ~10 years monthly, ~5 years daily


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_env(key: str, required: bool = True) -> str:
    """
    Retrieve an environment variable.

    Args:
        key: Environment variable name.
        required: If True, raises ValueError when missing.

    Returns:
        The value of the environment variable.

    Raises:
        ValueError: If required and not set.
    """
    value = os.environ.get(key, "")
    if required and not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value
