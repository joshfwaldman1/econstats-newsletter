"""
PDF chart extractor — downloads academic paper PDFs and uses
PyMuPDF (page rendering) + Claude Vision to identify and extract
the most relevant chart pages.

Designed for NBER working papers, Brookings reports, and similar
research PDFs that contain data visualizations.
"""

from __future__ import annotations

import base64
import io
import logging
import tempfile
from pathlib import Path

import anthropic
import fitz  # PyMuPDF
import requests
from PIL import Image

from config import CHART_MAX_SIZE_KB, CLAUDE_MODEL, get_env

logger = logging.getLogger(__name__)

# Maximum pages to scan in a PDF (papers rarely have charts past page 40)
MAX_PAGES_TO_SCAN: int = 40

# Resolution for page rendering
PAGE_DPI: int = 150

# Maximum chart images to extract per paper
MAX_CHARTS_PER_PAPER: int = 3


def download_pdf(pdf_url: str) -> bytes | None:
    """
    Download a PDF from a URL.

    Args:
        pdf_url: Direct URL to the PDF file.

    Returns:
        PDF bytes, or None on failure.
    """
    try:
        response = requests.get(pdf_url, timeout=30, stream=True)
        response.raise_for_status()

        # Verify it's actually a PDF
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type and not response.content[:5] == b"%PDF-":
            logger.warning("URL does not appear to be a PDF: %s", pdf_url)
            return None

        # Cap download size at 50MB
        max_size = 50 * 1024 * 1024
        if len(response.content) > max_size:
            logger.warning("PDF too large (%.1fMB): %s", len(response.content) / 1024 / 1024, pdf_url)
            return None

        logger.info("Downloaded PDF: %.1fMB from %s", len(response.content) / 1024 / 1024, pdf_url)
        return response.content

    except requests.RequestException:
        logger.warning("Failed to download PDF: %s", pdf_url, exc_info=True)
        return None


def render_pages_as_images(pdf_bytes: bytes) -> list[dict]:
    """
    Render each page of a PDF as a PNG image.

    Only renders up to MAX_PAGES_TO_SCAN pages.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        List of dicts with keys: page_number, image_bytes, width, height.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_images: list[dict] = []

    pages_to_scan = min(len(doc), MAX_PAGES_TO_SCAN)

    for page_num in range(pages_to_scan):
        page = doc[page_num]
        # Render at configured DPI
        mat = fitz.Matrix(PAGE_DPI / 72, PAGE_DPI / 72)
        pix = page.get_pixmap(matrix=mat)

        img_bytes = pix.tobytes("png")
        page_images.append({
            "page_number": page_num + 1,  # 1-indexed for display
            "image_bytes": img_bytes,
            "width": pix.width,
            "height": pix.height,
        })

    doc.close()
    logger.info("Rendered %d pages from PDF", len(page_images))
    return page_images


def identify_chart_pages(page_images: list[dict]) -> list[int]:
    """
    Use Claude Vision to identify which pages contain charts/figures.

    Sends a batch of page thumbnails to Claude and asks it to
    identify pages with data visualizations (charts, graphs, tables).

    Args:
        page_images: List of rendered page dicts from render_pages_as_images().

    Returns:
        List of 1-indexed page numbers that contain charts.
    """
    api_key = get_env("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    if not page_images:
        return []

    # Send up to 10 pages at a time (to stay under token limits)
    # Create thumbnails for efficiency
    content_blocks: list[dict] = []
    for page in page_images[:20]:  # Cap at 20 pages for cost
        # Resize to thumbnail for the identification pass
        thumbnail = _create_thumbnail(page["image_bytes"], max_width=400)
        b64_data = base64.b64encode(thumbnail).decode("utf-8")

        content_blocks.append({
            "type": "text",
            "text": f"Page {page['page_number']}:",
        })
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64_data,
            },
        })

    content_blocks.append({
        "type": "text",
        "text": (
            "Which of these pages contain charts, graphs, or data visualizations? "
            "Return ONLY a JSON array of page numbers, e.g. [3, 7, 12]. "
            "Exclude pages that only have text, tables of contents, or references. "
            "If no pages have charts, return []."
        ),
    })

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": content_blocks}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        # Parse the JSON array
        import json
        # Find the array in the response
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            page_numbers = json.loads(text[start : end + 1])
            if isinstance(page_numbers, list):
                return [int(p) for p in page_numbers if isinstance(p, (int, float))]

    except Exception:
        logger.warning("Chart page identification failed", exc_info=True)

    return []


def extract_charts(
    pdf_url: str,
    output_dir: str | Path = "output/charts",
    paper_id: str = "paper",
) -> list[dict]:
    """
    Full pipeline: download PDF → render pages → identify charts → save PNGs.

    Args:
        pdf_url: Direct URL to the PDF.
        output_dir: Directory to save extracted chart images.
        paper_id: Identifier for naming output files.

    Returns:
        List of dicts with keys: path, page_number, alt_text.
        Empty list if no charts found or extraction fails.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Step 1: Download
    pdf_bytes = download_pdf(pdf_url)
    if pdf_bytes is None:
        return []

    # Step 2: Render pages
    page_images = render_pages_as_images(pdf_bytes)
    if not page_images:
        return []

    # Step 3: Identify chart pages
    chart_pages = identify_chart_pages(page_images)
    if not chart_pages:
        logger.info("No chart pages identified in %s", paper_id)
        return []

    logger.info("Found charts on pages %s of %s", chart_pages, paper_id)

    # Step 4: Save the chart page images (limit to MAX_CHARTS_PER_PAPER)
    extracted: list[dict] = []
    for page_num in chart_pages[:MAX_CHARTS_PER_PAPER]:
        # Find the corresponding page image
        page_data = next(
            (p for p in page_images if p["page_number"] == page_num),
            None,
        )
        if page_data is None:
            continue

        # Optimize the image for email
        optimized = _optimize_for_email(page_data["image_bytes"])

        filename = f"{paper_id}_p{page_num}.png"
        filepath = output_path / filename

        with open(filepath, "wb") as f:
            f.write(optimized)

        file_size_kb = len(optimized) / 1024
        logger.info("Extracted chart: %s (%.0fKB)", filename, file_size_kb)

        extracted.append({
            "path": str(filepath.resolve()),
            "page_number": page_num,
            "alt_text": f"Figure from research paper (page {page_num})",
        })

    return extracted


def _create_thumbnail(image_bytes: bytes, max_width: int = 400) -> bytes:
    """
    Create a smaller thumbnail for the Claude Vision identification pass.

    Args:
        image_bytes: Original PNG image bytes.
        max_width: Maximum width in pixels.

    Returns:
        Resized PNG bytes.
    """
    img = Image.open(io.BytesIO(image_bytes))
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _optimize_for_email(image_bytes: bytes, max_width: int = 600) -> bytes:
    """
    Optimize a chart image for email embedding.

    Resizes to email width and compresses to stay under size limit.

    Args:
        image_bytes: Original PNG bytes.
        max_width: Target width in pixels.

    Returns:
        Optimized PNG bytes.
    """
    img = Image.open(io.BytesIO(image_bytes))

    # Resize if wider than email width
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    # Convert to RGB if RGBA (smaller file size, email doesn't need alpha)
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    result = output.getvalue()

    # If still too large, try JPEG
    if len(result) / 1024 > CHART_MAX_SIZE_KB:
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85, optimize=True)
        jpeg_result = output.getvalue()
        if len(jpeg_result) < len(result):
            return jpeg_result

    return result
