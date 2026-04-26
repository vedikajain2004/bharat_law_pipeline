"""
parsers/pdf_parser.py — PDF → Markdown normalizer

Design choices:
- PyMuPDF (fitz) chosen over pdfminer for speed and layout fidelity
- Reconstructs paragraphs by grouping text blocks on the same logical line
  (using y-coordinate proximity within a tolerance)
- Heading detection: blocks whose font size is ≥ 1.15× the modal body font size
  are treated as headings; depth (H1/H2/H3) mapped from relative size rank
- Page numbers are injected as HTML comments <!-- page N --> so the chunker
  can track them without polluting visible text
- Two-column PDFs: blocks are sorted by (column, y) using page midpoint as
  the column boundary
"""

import hashlib
import json
import logging
import re
import statistics
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _modal_font_size(blocks: list) -> float:
    """Return the most common font size in the page (proxy for body text size)."""
    sizes = []
    for b in blocks:
        if b["type"] != 0:  # 0 = text block
            continue
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                sizes.append(round(span.get("size", 12), 1))
    if not sizes:
        return 12.0
    try:
        return statistics.mode(sizes)
    except statistics.StatisticsError:
        return sorted(sizes)[len(sizes) // 2]


def _block_text(block: dict) -> str:
    """Extract raw text from a PyMuPDF text block dict."""
    parts = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            parts.append(span.get("text", ""))
    return "".join(parts).strip()


def _block_max_font(block: dict) -> float:
    """Max font size within a block."""
    sizes = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            sizes.append(span.get("size", 12))
    return max(sizes) if sizes else 12.0


def _heading_level(font_size: float, modal: float) -> Optional[int]:
    """
    Return heading level (1, 2, 3) or None for body text.
    Threshold: block font ≥ 1.15× modal → heading.
    """
    ratio = font_size / modal if modal else 1.0
    if ratio >= 1.5:
        return 1
    elif ratio >= 1.25:
        return 2
    elif ratio >= 1.15:
        return 3
    return None


def _sort_blocks_two_col(blocks: list, page_width: float) -> list:
    """Sort blocks for two-column layout: left col top-to-bottom, then right col."""
    mid = page_width / 2
    left  = [b for b in blocks if b["bbox"][0] < mid]
    right = [b for b in blocks if b["bbox"][0] >= mid]
    left.sort(key=lambda b: b["bbox"][1])
    right.sort(key=lambda b: b["bbox"][1])
    return left + right


def _clean_text(text: str) -> str:
    """Normalize whitespace, fix ligatures."""
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ── Per-page conversion ───────────────────────────────────────────────────────

def _page_to_markdown(page, page_num: int) -> str:
    """Convert a single fitz.Page to Markdown string."""
    page_dict = page.get_text("dict", flags=~0)  # full detail
    blocks = [b for b in page_dict.get("blocks", []) if b["type"] == 0]
    if not blocks:
        return ""

    modal = _modal_font_size(blocks)
    page_width = page.rect.width

    # Detect two-column layout heuristically
    x_positions = [b["bbox"][0] for b in blocks]
    unique_cols = len(set(round(x / 50) for x in x_positions))
    if unique_cols >= 4:          # many distinct x-origins → likely 2-col
        blocks = _sort_blocks_two_col(blocks, page_width)
    else:
        blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

    lines = [f"\n<!-- page {page_num} -->\n"]
    prev_y_bottom = -1

    for block in blocks:
        text = _clean_text(_block_text(block))
        if not text or len(text) < 2:
            continue

        max_fs = _block_max_font(block)
        level  = _heading_level(max_fs, modal)

        # Add vertical gap if blocks are far apart
        top = block["bbox"][1]
        if prev_y_bottom >= 0 and (top - prev_y_bottom) > modal * 1.8:
            lines.append("")
        prev_y_bottom = block["bbox"][3]

        if level == 1:
            lines.append(f"\n# {text}\n")
        elif level == 2:
            lines.append(f"\n## {text}\n")
        elif level == 3:
            lines.append(f"\n### {text}\n")
        else:
            lines.append(text)

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def parse_pdf(
    pdf_path: Path,
    url: str,
    url_hash: Optional[str] = None,
    out_dir: Optional[Path] = None,
) -> dict:
    """
    Parse a PDF file into clean Markdown.

    Returns a metadata dict suitable for normalized_index.jsonl.
    If out_dir is provided, writes the markdown file there.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ImportError("PyMuPDF not installed. Run: pip install pymupdf") from e

    if url_hash is None:
        url_hash = hashlib.md5(url.encode()).hexdigest()[:16]

    doc = fitz.open(str(pdf_path))
    sections = []

    for page_num, page in enumerate(doc, start=1):
        page_md = _page_to_markdown(page, page_num)
        if page_md.strip():
            sections.append(page_md)

    doc.close()

    md = "\n\n".join(sections)
    # Collapse excessive blank lines
    md = re.sub(r"\n{4,}", "\n\n\n", md)

    # Attempt title from PDF metadata, then first H1 in content
    title = _extract_pdf_title(pdf_path, md, url)

    # Language detection
    lang = _detect_language(md)

    record = {
        "url":               url,
        "url_hash":          url_hash,
        "source_type":       "pdf",
        "title":             title,
        "detected_language": lang,
        "char_count":        len(md),
        "path_to_text":      "",
    }

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"{url_hash}.md"
        md_path.write_text(md, encoding="utf-8")
        record["path_to_text"] = str(md_path)
        logger.info(f"PDF parsed → {md_path}  ({len(md):,} chars, {len(sections)} pages)")

    return record


def _extract_pdf_title(pdf_path: Path, md: str, url: str) -> str:
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        meta = doc.metadata
        doc.close()
        if meta.get("title", "").strip():
            return meta["title"].strip()
    except Exception:
        pass

    # Fall back to first H1 in extracted text
    m = re.search(r"^#\s+(.+)$", md, re.M)
    if m:
        return m.group(1).strip()

    # Last resort: filename
    return pdf_path.stem.replace("-", " ").replace("_", " ").title()


def _detect_language(text: str) -> str:
    try:
        from langdetect import detect
        sample = text[:2000].strip()
        if len(sample) > 20:
            return detect(sample)
    except Exception:
        pass
    return "en"
