"""
EconStats Daily Newsletter — 10-step pipeline orchestrator.

Fetches news → discovers papers → deduplicates → curates with Claude →
fetches FRED data → renders charts → extracts paper charts →
deploys images → builds email → sends via Gmail.

Usage:
    python main.py                 # Run the full pipeline
    python main.py --test-chart    # Test: render a single FRED chart
    python main.py --test-email    # Test: send a static test email
"""

from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv

from config import FUZZY_MATCH_THRESHOLD, SOURCE_PRIORITY

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("newsletter")


# ---------------------------------------------------------------------------
# Deduplication (ported from daily-news-tracker)
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    """Normalize a headline for fuzzy matching."""
    title = title.lower().strip()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def _source_rank(source: str) -> int:
    """Get priority rank for a news source (higher = more authoritative)."""
    for key, rank in SOURCE_PRIORITY.items():
        if key.lower() in source.lower():
            return rank
    return 3  # default for unknown sources


def deduplicate(articles: list[dict]) -> list[dict]:
    """
    Remove duplicate articles using fuzzy title matching + source priority.

    Sorts by source authority (highest first), then keeps the first
    instance of each story. Duplicates are detected via SequenceMatcher
    with a configurable similarity threshold.

    Args:
        articles: Raw combined articles from all sources.

    Returns:
        Deduplicated list with highest-authority source versions kept.
    """
    # Sort by source rank (highest priority first)
    sorted_articles = sorted(articles, key=lambda a: _source_rank(a.get("source", "")), reverse=True)

    kept: list[dict] = []
    kept_normalized: list[str] = []

    for article in sorted_articles:
        title = article.get("title", "")
        if not title:
            continue

        norm = _normalize_title(title)

        # Check against all kept titles
        is_duplicate = False
        for existing_norm in kept_normalized:
            similarity = SequenceMatcher(None, norm, existing_norm).ratio()
            if similarity >= FUZZY_MATCH_THRESHOLD:
                is_duplicate = True
                break

        if not is_duplicate:
            kept.append(article)
            kept_normalized.append(norm)

    logger.info("Dedup: %d → %d articles (removed %d duplicates)", len(articles), len(kept), len(articles) - len(kept))
    return kept


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full 11-step newsletter pipeline."""
    load_dotenv()

    logger.info("=" * 60)
    logger.info("EconStats Daily Newsletter — %s", datetime.now().strftime("%A, %B %d, %Y"))
    logger.info("=" * 60)

    # Apply chart styling once at startup
    from charts.style import apply_newsletter_style
    apply_newsletter_style()

    # ── Step 1: Fetch articles from all sources ────────────────────────
    logger.info("Step 1/11: Fetching articles...")

    from sources.newsapi_source import fetch_newsapi_articles
    from sources.rss_source import fetch_rss_articles
    from sources.web_research_source import fetch_web_research_articles
    from sources.nber_source import fetch_nber_papers

    newsapi_articles = fetch_newsapi_articles()
    rss_articles = fetch_rss_articles()
    research_articles = fetch_web_research_articles()
    nber_papers = fetch_nber_papers()

    # Combine all sources
    all_articles = newsapi_articles + rss_articles + research_articles + nber_papers
    logger.info(
        "Fetched: NewsAPI=%d, RSS=%d, Research=%d, NBER=%d → Total=%d",
        len(newsapi_articles), len(rss_articles), len(research_articles),
        len(nber_papers), len(all_articles),
    )

    if not all_articles:
        logger.error("No articles fetched from any source — aborting")
        sys.exit(1)

    # ── Step 2: Deduplicate ────────────────────────────────────────────
    logger.info("Step 2/11: Deduplicating...")
    unique_articles = deduplicate(all_articles)

    if len(unique_articles) < 5:
        logger.error("Only %d unique articles — too few to build a newsletter", len(unique_articles))
        sys.exit(1)

    # ── Step 3: Curate with Claude ─────────────────────────────────────
    logger.info("Step 3/11: Curating with Claude...")
    from curation.curator import curate_newsletter
    curation = curate_newsletter(unique_articles)

    if curation is None:
        logger.error("Curation failed — aborting")
        sys.exit(1)

    chart_of_the_day = curation.get("chart_of_the_day", {})
    from_the_research = curation.get("from_the_research", [])
    in_the_data = curation.get("in_the_data", [])
    headlines_list = curation.get("headlines", [])

    # ── Step 4: Collect FRED series IDs needed ─────────────────────────
    logger.info("Step 4/11: Identifying FRED series to fetch...")
    series_ids_needed: list[str] = []

    # Chart of the Day
    cotd_series = chart_of_the_day.get("series_id")
    if cotd_series:
        series_ids_needed.append(cotd_series)

    # In the Data stories
    for story in in_the_data:
        sid = story.get("series_id")
        if sid and sid not in series_ids_needed:
            series_ids_needed.append(sid)

    # Research papers with FRED mapping
    for paper in from_the_research:
        sid = paper.get("series_id")
        if sid and sid not in series_ids_needed:
            series_ids_needed.append(sid)

    logger.info("Need %d FRED series: %s", len(series_ids_needed), ", ".join(series_ids_needed))

    # ── Step 5: Fetch FRED data ────────────────────────────────────────
    logger.info("Step 5/11: Fetching FRED data...")
    from fred.client import fetch_series
    from fred.registry import get_default_transform, lookup

    series_data_map: dict[str, any] = {}
    for series_id in series_ids_needed:
        try:
            transform = get_default_transform(series_id)
            data = fetch_series(series_id, units=transform)
            series_data_map[series_id] = data
        except Exception:
            logger.warning("Failed to fetch FRED series %s", series_id, exc_info=True)

    logger.info("Fetched %d/%d FRED series", len(series_data_map), len(series_ids_needed))

    # ── Step 6: Render FRED charts ─────────────────────────────────────
    logger.info("Step 6/11: Rendering FRED charts...")
    from charts.fred_chart import render_chart

    output_dir = Path("output/charts")
    chart_results: dict[str, dict] = {}  # series_id → render result

    # Collect custom chart titles from curation (COTD may have a custom title)
    custom_chart_titles: dict[str, str] = {}
    cotd_chart_title = chart_of_the_day.get("chart_title")
    if cotd_chart_title and cotd_series:
        custom_chart_titles[cotd_series] = cotd_chart_title

    for i, (series_id, data) in enumerate(series_data_map.items()):
        title_override = custom_chart_titles.get(series_id)
        result = render_chart(
            data, output_dir=output_dir, color_index=i,
            title_override=title_override,
        )
        if result:
            chart_results[series_id] = result

    logger.info("Rendered %d charts", len(chart_results))

    # ── Step 7: Extract paper charts (if any) ──────────────────────────
    logger.info("Step 7/11: Extracting paper charts...")
    from charts.paper_extractor import extract_charts

    paper_chart_results: list[dict] = []
    for paper in from_the_research:
        if not paper.get("has_charts"):
            continue

        # Look for PDF URL in NBER papers
        paper_url = paper.get("url", "")
        pdf_url = None

        # Check if we have a matching NBER paper with verified PDF
        for nber_paper in nber_papers:
            if nber_paper.get("url") == paper_url and nber_paper.get("pdf_url"):
                pdf_url = nber_paper["pdf_url"]
                break

        if pdf_url:
            paper_id = nber_paper.get("paper_id", "paper")
            extracted = extract_charts(pdf_url, output_dir=output_dir, paper_id=paper_id)
            paper_chart_results.extend(extracted)

    logger.info("Extracted %d paper charts", len(paper_chart_results))

    # ── Step 8: Deploy charts to GitHub Pages ──────────────────────────
    logger.info("Step 8/11: Deploying charts...")
    from deploy.github_pages import deploy_charts

    # Collect all chart file paths
    all_chart_paths = [r["path"] for r in chart_results.values() if r.get("path")]
    all_chart_paths += [r["path"] for r in paper_chart_results if r.get("path")]

    deployed_urls_raw = deploy_charts(all_chart_paths)

    # Build series_id → URL mapping for the email builder
    chart_urls: dict[str, str] = {}
    chart_alt_texts: dict[str, str] = {}
    for series_id, result in chart_results.items():
        filename = Path(result["path"]).name
        url = deployed_urls_raw.get(filename, "")
        if url:
            chart_urls[series_id] = url
        chart_alt_texts[series_id] = result.get("alt_text", "")

    logger.info("Chart URLs mapped for %d series", len(chart_urls))

    # ── Step 9: Generate chart annotations (with GROUND TRUTH) ──────────
    logger.info("Step 9/11: Generating annotations with ground-truth data...")
    from curation.curator import generate_annotation, generate_cotd_context
    from fred.transforms import format_value, get_change_summary

    # 9a: Regenerate COTD context grounded in REAL data
    if cotd_series and cotd_series in chart_results:
        cotd_result = chart_results[cotd_series]
        cotd_data = series_data_map.get(cotd_series)
        reg = lookup(cotd_series)

        if cotd_data and reg:
            # Build a summary of recent observations for context
            valid_obs = [o for o in cotd_data.observations if o.value is not None]
            recent = valid_obs[-6:] if len(valid_obs) >= 6 else valid_obs
            obs_summary = ", ".join(
                f"{o.date}: {format_value(o.value, reg.unit_type, reg.default_transform)}"
                for o in recent
            )

            new_context = generate_cotd_context(
                series_id=cotd_series,
                series_name=reg.display_name or reg.name,
                latest_value=cotd_result.get("latest_value", "N/A"),
                latest_date=cotd_result.get("latest_date", ""),
                source_headline=chart_of_the_day.get("source_headline", chart_of_the_day.get("headline", "")),
                our_headline=chart_of_the_day.get("headline", ""),
                observations_summary=obs_summary,
            )
            chart_of_the_day["context"] = new_context
            logger.info("COTD context regenerated with ground-truth data")

    # 9b: Annotate "In the Data" stories
    # ALWAYS overwrite annotations when FRED data is available — the initial
    # curation pass writes annotations from training data (no FRED access),
    # which can hallucinate values (e.g., wrong GDP quarter). Ground-truth
    # annotations from actual FRED data must take precedence.
    for story in in_the_data:
        series_id = story.get("series_id", "")
        result = chart_results.get(series_id)
        if result:
            reg = lookup(series_id)
            series_name = reg.name if reg else series_id
            annotation = generate_annotation(
                series_id=series_id,
                series_name=series_name,
                latest_value=result.get("latest_value", "N/A"),
                latest_date=result.get("latest_date", ""),
                headline=story.get("headline", ""),
            )
            story["annotation"] = annotation
            logger.info("Annotation grounded for %s (%s)", series_id, story.get("headline", "")[:50])

    # ── Step 10: Chief Economist review ────────────────────────────────
    logger.info("Step 10/11: Chief Economist review (fact-check + quality gate)...")
    from curation.reviewer import review_newsletter, apply_fixes, build_ground_truth_summary

    ground_truth = build_ground_truth_summary(series_data_map, chart_results, lookup)

    review = review_newsletter(
        chart_of_the_day=chart_of_the_day,
        from_the_research=from_the_research,
        in_the_data=in_the_data,
        headlines=headlines_list,
        ground_truth_summary=ground_truth,
    )

    verdict = review.get("verdict", "pass")
    issues = review.get("issues_found", [])
    notes = review.get("reviewer_notes", "")
    critical_count = sum(1 for i in issues if i.get("severity") == "critical")
    warning_count = sum(1 for i in issues if i.get("severity") == "warning")

    logger.info(
        "Review verdict: %s | %d critical, %d warnings | %s",
        verdict.upper(), critical_count, warning_count, notes,
    )

    # Log each issue
    for issue in issues:
        level = logging.ERROR if issue.get("severity") == "critical" else logging.WARNING
        logger.log(
            level,
            "REVIEW [%s] %s.%s: %s",
            issue.get("severity", "?").upper(),
            issue.get("section", "?"),
            issue.get("field", "?"),
            issue.get("problem", "no description"),
        )

    # Apply critical fixes (modifies dicts in place)
    if critical_count > 0:
        fixes_applied = apply_fixes(review, chart_of_the_day, from_the_research, in_the_data, headlines_list)
        logger.info("Applied %d/%d critical fixes", fixes_applied, critical_count)

    # ── Step 11: Build and send email ──────────────────────────────────
    logger.info("Step 11/11: Building and sending email...")
    from email_builder.template import build_email
    from email_builder.sender import send_newsletter

    html_body, plain_text_body = build_email(
        chart_of_the_day=chart_of_the_day,
        from_the_research=from_the_research,
        in_the_data=in_the_data,
        headlines=headlines_list,
        chart_urls=chart_urls,
        chart_alt_texts=chart_alt_texts,
    )

    success = send_newsletter(html_body, plain_text_body)

    if success:
        logger.info("Newsletter sent successfully!")
    else:
        logger.error("Failed to send newsletter")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Pipeline complete")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Test modes
# ---------------------------------------------------------------------------

def test_chart() -> None:
    """Test: fetch UNRATE from FRED and render a chart."""
    load_dotenv()

    from charts.style import apply_newsletter_style
    apply_newsletter_style()

    from fred.client import fetch_series
    from fred.registry import get_default_transform
    from charts.fred_chart import render_chart

    series_id = "UNRATE"
    transform = get_default_transform(series_id)
    data = fetch_series(series_id, units=transform)

    result = render_chart(data)
    if result:
        print(f"Chart saved to: {result['path']}")
        print(f"Alt text: {result['alt_text']}")
    else:
        print("Failed to render chart")


def test_email() -> None:
    """Test: send a static test email with placeholder data."""
    load_dotenv()

    from email_builder.template import build_email
    from email_builder.sender import send_newsletter

    # Static test data
    cotd = {
        "headline": "Unemployment Holds Steady at 3.7%",
        "source": "BLS",
        "url": "https://www.bls.gov/news.release/empsit.nr0.htm",
        "series_id": "UNRATE",
        "context": "The unemployment rate was unchanged at 3.7% in January. "
                   "Nonfarm payroll employment rose by 353,000, well above expectations. "
                   "The labor market continues to show resilience despite higher interest rates.",
        "cta_text": "Explore unemployment trends on econstats.org",
    }

    research = [
        {
            "title": "The Long-Run Effects of Monetary Policy",
            "source": "NBER",
            "url": "https://www.nber.org/papers/w30000",
            "summary": "This paper examines how monetary policy affects long-run growth. "
                       "The authors find that extended periods of low rates can reduce productivity growth.",
            "series_id": None,
            "has_charts": False,
        }
    ]

    data_stories = [
        {
            "headline": "Fed Holds Rates Steady, Signals Patience",
            "source": "WSJ",
            "url": "https://www.wsj.com/",
            "series_id": "FEDFUNDS",
            "annotation": "The fed funds rate remains at 5.33%, the highest level since 2001.",
        },
        {
            "headline": "Inflation Continues Gradual Decline",
            "source": "Reuters",
            "url": "https://www.reuters.com/",
            "series_id": "CPIAUCSL",
            "annotation": "CPI inflation fell to 3.1% year-over-year, down from its 9.1% peak in June 2022.",
        },
    ]

    headline_list = [
        {"headline": "OpenAI Launches New Model", "source": "Bloomberg", "url": "#", "category": "AI"},
        {"headline": "EU Tariffs on Chinese EVs", "source": "FT", "url": "#", "category": "Tariffs/International"},
        {"headline": "Housing Starts Fall 4%", "source": "Reuters", "url": "#", "category": "Other Econ"},
    ]

    html, plain = build_email(
        chart_of_the_day=cotd,
        from_the_research=research,
        in_the_data=data_stories,
        headlines=headline_list,
        chart_urls={},      # No charts in test mode
        chart_alt_texts={},
    )

    print(f"HTML size: {len(html.encode('utf-8')) / 1024:.1f}KB")
    print(f"Plain text size: {len(plain.encode('utf-8')) / 1024:.1f}KB")

    success = send_newsletter(html, plain)
    print(f"Send result: {'success' if success else 'failed'}")


if __name__ == "__main__":
    if "--test-chart" in sys.argv:
        test_chart()
    elif "--test-email" in sys.argv:
        test_email()
    else:
        main()
