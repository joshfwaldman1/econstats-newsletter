"""
Table-based HTML email builder for the EconStats Daily newsletter.

Produces email-client-safe HTML using inline CSS and table layout.
Handles Outlook's Word rendering engine, Gmail's CSS stripping,
and image-blocked clients (via rich alt text).
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def build_email(
    chart_of_the_day: dict,
    from_the_research: list[dict],
    in_the_data: list[dict],
    headlines: list[dict],
    chart_urls: dict[str, str],
    chart_alt_texts: dict[str, str],
) -> tuple[str, str]:
    """
    Build the complete newsletter email in HTML and plain-text formats.

    Args:
        chart_of_the_day: Dict with headline, source, url, series_id, context, cta_text.
        from_the_research: List of research paper dicts.
        in_the_data: List of data story dicts with chart references.
        headlines: List of headline dicts with categories.
        chart_urls: Mapping of series_id → hosted image URL.
        chart_alt_texts: Mapping of series_id → alt text.

    Returns:
        Tuple of (html_body, plain_text_body).
    """
    today = datetime.now().strftime("%A, %B %d, %Y")

    html = _build_html(
        today, chart_of_the_day, from_the_research, in_the_data,
        headlines, chart_urls, chart_alt_texts,
    )
    plain = _build_plain_text(
        today, chart_of_the_day, from_the_research, in_the_data, headlines,
    )

    # Check Gmail clipping threshold
    html_size_kb = len(html.encode("utf-8")) / 1024
    if html_size_kb > 102:
        logger.warning(
            "HTML email is %.0fKB — exceeds Gmail's 102KB clipping threshold!",
            html_size_kb,
        )

    return html, plain


def _build_html(
    today: str,
    cotd: dict,
    research: list[dict],
    data_stories: list[dict],
    headlines: list[dict],
    chart_urls: dict[str, str],
    chart_alt_texts: dict[str, str],
) -> str:
    """Build the HTML version of the newsletter."""

    # Group headlines by category
    headlines_by_cat: dict[str, list[dict]] = {}
    for h in headlines:
        cat = h.get("category", "Other Econ")
        headlines_by_cat.setdefault(cat, []).append(h)

    # ── Header ─────────────────────────────────────────────────────────
    html_parts: list[str] = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>',
        '<body style="margin: 0; padding: 0; background-color: #f5f5f0;">',
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f0;">',
        '<tr><td align="center" style="padding: 20px 10px;">',
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; max-width: 600px;">',
        # Header
        '<tr><td style="padding: 32px 40px 0 40px;">',
        f'<h1 style="font-family: Georgia, \'Times New Roman\', serif; font-size: 22px; color: #1a1a1a; '
        f'border-bottom: 2px solid #333; padding-bottom: 10px; margin: 0 0 6px 0;">EconStats Daily</h1>',
        f'<p style="font-family: Georgia, serif; font-size: 13px; color: #888; margin: 0 0 28px 0;">{today}</p>',
        '</td></tr>',
    ]

    # ── Section 1: Chart of the Day ────────────────────────────────────
    if cotd:
        series_id = cotd.get("series_id", "")
        chart_url = chart_urls.get(series_id, "")
        alt_text = chart_alt_texts.get(series_id, f"Chart: {series_id}")

        html_parts.append('<tr><td style="padding: 0 40px;">')
        html_parts.append(
            '<h2 style="font-family: Georgia, serif; font-size: 14px; color: #B2182B; '
            'text-transform: uppercase; letter-spacing: 1px; margin: 0 0 14px 0;">Chart of the Day</h2>'
        )
        # Headline
        headline = cotd.get("headline", "")
        source = cotd.get("source", "")
        url = cotd.get("url", "")
        html_parts.append(
            f'<p style="font-family: Georgia, serif; font-size: 13px; color: #666; '
            f'text-transform: uppercase; letter-spacing: 0.3px; margin: 0 0 4px 0; font-weight: bold;">{source}</p>'
        )
        html_parts.append(
            f'<p style="font-family: Georgia, serif; font-size: 17px; color: #1a1a1a; '
            f'margin: 0 0 12px 0; font-weight: 600; line-height: 1.4;">'
            f'<a href="{url}" style="color: #1a1a1a; text-decoration: none;">{headline}</a></p>'
        )
        # Chart image
        if chart_url:
            html_parts.append(
                f'<img src="{chart_url}" alt="{alt_text}" width="520" '
                f'style="width: 100%; max-width: 520px; height: auto; display: block; margin: 0 0 12px 0; '
                f'border: 1px solid #eee;">'
            )
        # Context
        context = cotd.get("context", "")
        html_parts.append(
            f'<p style="font-family: Georgia, serif; font-size: 15px; color: #333; '
            f'line-height: 1.6; margin: 0 0 16px 0;">{context}</p>'
        )
        # CTA button
        cta_text = cotd.get("cta_text", "Explore on econstats.org")
        html_parts.append(
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 0 0 24px 0;">'
            '<tr><td style="background-color: #2166AC; border-radius: 4px; padding: 10px 20px;">'
            f'<a href="https://econstats.org" style="color: #ffffff; font-family: Georgia, serif; '
            f'font-size: 14px; text-decoration: none; font-weight: bold;">{cta_text}</a>'
            '</td></tr></table>'
        )
        # Divider
        html_parts.append(
            '<hr style="border: none; border-top: 1px solid #ddd; margin: 8px 0 24px 0;">'
        )
        html_parts.append('</td></tr>')

    # ── Section 2: From the Research ───────────────────────────────────
    if research:
        html_parts.append('<tr><td style="padding: 0 40px;">')
        html_parts.append(
            '<h2 style="font-family: Georgia, serif; font-size: 14px; color: #1B7837; '
            'text-transform: uppercase; letter-spacing: 1px; margin: 0 0 14px 0;">From the Research</h2>'
        )
        for paper in research:
            title = paper.get("title", "")
            source = paper.get("source", "")
            url = paper.get("url", "")
            summary = paper.get("summary", "")
            paper_series = paper.get("series_id")
            paper_chart_url = chart_urls.get(paper_series, "") if paper_series else ""
            paper_alt = chart_alt_texts.get(paper_series, "") if paper_series else ""

            html_parts.append(
                f'<p style="font-family: Georgia, serif; font-size: 13px; color: #666; '
                f'text-transform: uppercase; letter-spacing: 0.3px; margin: 0 0 4px 0; font-weight: bold;">{source}</p>'
            )
            html_parts.append(
                f'<p style="font-family: Georgia, serif; font-size: 16px; margin: 0 0 8px 0; line-height: 1.4;">'
                f'<a href="{url}" style="color: #0066cc; text-decoration: none; font-weight: 600;">{title}</a></p>'
            )
            if paper_chart_url:
                html_parts.append(
                    f'<img src="{paper_chart_url}" alt="{paper_alt}" width="520" '
                    f'style="width: 100%; max-width: 520px; height: auto; display: block; margin: 0 0 8px 0; '
                    f'border: 1px solid #eee;">'
                )
            html_parts.append(
                f'<p style="font-family: Georgia, serif; font-size: 14px; color: #444; '
                f'line-height: 1.6; margin: 0 0 20px 0;">{summary}</p>'
            )
        html_parts.append(
            '<hr style="border: none; border-top: 1px solid #ddd; margin: 4px 0 24px 0;">'
        )
        html_parts.append('</td></tr>')

    # ── Section 3: In the Data ─────────────────────────────────────────
    if data_stories:
        html_parts.append('<tr><td style="padding: 0 40px;">')
        html_parts.append(
            '<h2 style="font-family: Georgia, serif; font-size: 14px; color: #2166AC; '
            'text-transform: uppercase; letter-spacing: 1px; margin: 0 0 14px 0;">In the Data</h2>'
        )
        for story in data_stories:
            headline = story.get("headline", "")
            source = story.get("source", "")
            url = story.get("url", "")
            series_id = story.get("series_id", "")
            annotation = story.get("annotation", "")
            story_chart_url = chart_urls.get(series_id, "")
            story_alt = chart_alt_texts.get(series_id, "")

            html_parts.append(
                f'<p style="font-family: Georgia, serif; font-size: 13px; color: #666; '
                f'text-transform: uppercase; letter-spacing: 0.3px; margin: 0 0 4px 0; font-weight: bold;">{source}</p>'
            )
            html_parts.append(
                f'<p style="font-family: Georgia, serif; font-size: 15px; margin: 0 0 8px 0; line-height: 1.4;">'
                f'<a href="{url}" style="color: #0066cc; text-decoration: none; font-weight: 600;">{headline}</a></p>'
            )
            if story_chart_url:
                html_parts.append(
                    f'<img src="{story_chart_url}" alt="{story_alt}" width="520" '
                    f'style="width: 100%; max-width: 520px; height: auto; display: block; margin: 0 0 8px 0; '
                    f'border: 1px solid #eee;">'
                )
            if annotation:
                html_parts.append(
                    f'<p style="font-family: Georgia, serif; font-size: 14px; color: #444; '
                    f'font-style: italic; line-height: 1.5; margin: 0 0 20px 0;">{annotation}</p>'
                )
        html_parts.append(
            '<hr style="border: none; border-top: 1px solid #ddd; margin: 4px 0 24px 0;">'
        )
        html_parts.append('</td></tr>')

    # ── Section 4: Headlines ───────────────────────────────────────────
    if headlines_by_cat:
        html_parts.append('<tr><td style="padding: 0 40px;">')
        html_parts.append(
            '<h2 style="font-family: Georgia, serif; font-size: 14px; color: #333; '
            'text-transform: uppercase; letter-spacing: 1px; margin: 0 0 14px 0;">Headlines</h2>'
        )

        category_order = [
            "AI", "Tariffs/International", "Other Econ",
            "Research & Papers", "Non-Econ",
        ]
        for cat in category_order:
            cat_headlines = headlines_by_cat.get(cat, [])
            if not cat_headlines:
                continue

            html_parts.append(
                f'<h3 style="font-family: Georgia, serif; font-size: 13px; color: #333; '
                f'margin: 16px 0 10px 0; text-transform: uppercase; letter-spacing: 0.5px;">{cat}</h3>'
            )
            html_parts.append(
                '<ul style="list-style: none; padding-left: 0; margin: 0 0 0 4px;">'
            )
            for h in cat_headlines:
                h_headline = h.get("headline", "")
                h_source = h.get("source", "")
                h_url = h.get("url", "")
                html_parts.append(
                    f'<li style="margin-bottom: 14px; line-height: 1.5; font-size: 15px; '
                    f'padding-left: 12px; border-left: 3px solid #ddd;">'
                    f'<span style="color: #666; font-size: 12px; font-weight: bold; '
                    f'text-transform: uppercase; letter-spacing: 0.3px; font-family: Georgia, serif;">'
                    f'{h_source}</span><br>'
                    f'<a href="{h_url}" style="color: #0066cc; text-decoration: none; '
                    f'font-weight: 600; font-family: Georgia, serif;">{h_headline}</a>'
                    f'</li>'
                )
            html_parts.append('</ul>')

        html_parts.append('</td></tr>')

    # ── Footer ─────────────────────────────────────────────────────────
    total_stories = 1 + len(from_the_research or []) + len(in_the_data or []) + len(headlines or [])

    html_parts.extend([
        '<tr><td style="padding: 24px 40px 32px 40px;">',
        '<hr style="border: none; border-top: 1px solid #ccc; margin: 0 0 16px 0;">',
        '<p style="font-family: Georgia, serif; font-size: 12px; color: #888; margin: 0 0 8px 0; text-align: center;">',
        f'Charts powered by <a href="https://fred.stlouisfed.org" style="color: #888;">FRED</a> · '
        f'Curated with AI · {total_stories} stories',
        '</p>',
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 12px auto 0 auto;">'
        '<tr><td style="background-color: #2166AC; border-radius: 4px; padding: 10px 24px;">'
        '<a href="https://econstats.org" style="color: #ffffff; font-family: Georgia, serif; '
        'font-size: 14px; text-decoration: none; font-weight: bold;">Explore more at econstats.org</a>'
        '</td></tr></table>',
        '</td></tr>',
        '</table>',
        '</td></tr></table>',
        '</body></html>',
    ])

    return "\n".join(html_parts)


def _build_plain_text(
    today: str,
    cotd: dict,
    research: list[dict],
    data_stories: list[dict],
    headlines: list[dict],
) -> str:
    """Build the plain-text fallback version of the newsletter."""

    lines: list[str] = [
        f"EconStats Daily — {today}",
        "=" * 50,
        "",
    ]

    # Chart of the Day
    if cotd:
        lines.append("CHART OF THE DAY")
        lines.append("-" * 30)
        lines.append(f"  [{cotd.get('source', '')}] {cotd.get('headline', '')}")
        lines.append(f"    {cotd.get('url', '')}")
        lines.append(f"    Chart: FRED/{cotd.get('series_id', '')}")
        lines.append(f"    {cotd.get('context', '')}")
        lines.append("")

    # From the Research
    if research:
        lines.append("FROM THE RESEARCH")
        lines.append("-" * 30)
        for paper in research:
            lines.append(f"  [{paper.get('source', '')}] {paper.get('title', '')}")
            lines.append(f"    {paper.get('url', '')}")
            lines.append(f"    {paper.get('summary', '')}")
            lines.append("")

    # In the Data
    if data_stories:
        lines.append("IN THE DATA")
        lines.append("-" * 30)
        for story in data_stories:
            lines.append(f"  [{story.get('source', '')}] {story.get('headline', '')}")
            lines.append(f"    {story.get('url', '')}")
            lines.append(f"    Chart: FRED/{story.get('series_id', '')}")
            lines.append(f"    {story.get('annotation', '')}")
            lines.append("")

    # Headlines
    if headlines:
        lines.append("HEADLINES")
        lines.append("-" * 30)
        headlines_by_cat: dict[str, list[dict]] = {}
        for h in headlines:
            cat = h.get("category", "Other Econ")
            headlines_by_cat.setdefault(cat, []).append(h)

        for cat in ["AI", "Tariffs/International", "Other Econ", "Research & Papers", "Non-Econ"]:
            cat_headlines = headlines_by_cat.get(cat, [])
            if cat_headlines:
                lines.append(f"\n  {cat}")
                for h in cat_headlines:
                    lines.append(f"    [{h.get('source', '')}] {h.get('headline', '')}")
                    lines.append(f"      {h.get('url', '')}")

    lines.extend([
        "",
        "-" * 50,
        "Charts powered by FRED | Curated with AI",
        "Explore more at econstats.org",
    ])

    return "\n".join(lines)
