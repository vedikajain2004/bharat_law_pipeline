"""
parsers/run_parsers.py — Orchestrator for HTML and PDF parsing

Reads crawl_index.jsonl, dispatches to html_parser or pdf_parser,
writes normalized_index.jsonl.
"""

import json
import logging
from pathlib import Path

from parsers.html_parser import parse_html
from parsers.pdf_parser import parse_pdf

logger = logging.getLogger(__name__)


def run(
    raw_dir: Path,
    crawl_index: Path,
    normalized_dir: Path,
    normalized_index: Path,
) -> int:
    records = []

    with open(crawl_index, encoding="utf-8") as f:
        crawl_records = [json.loads(line) for line in f if line.strip()]

    for rec in crawl_records:
        # ── Guard: skip malformed index records ───────────────────────────────
        if not isinstance(rec, dict):
            logger.warning(f"Skipping non-dict record: {rec!r}")
            continue

        url      = rec.get("url", "")
        raw_str  = rec.get("path_to_raw", "")
        ctype    = rec.get("content_type", "")

        if not url or not raw_str:
            logger.warning(f"Record missing url or path_to_raw: {rec}")
            continue

        raw_path = Path(raw_str)
        # url_hash = stem of the raw filename (e.g. "abc123" from "raw/abc123.html")
        url_hash = raw_path.stem

        if not raw_path.exists():
            logger.warning(f"Missing raw file: {raw_path}  (url={url})")
            continue

        try:
            is_pdf = raw_str.endswith(".pdf") or "application/pdf" in ctype
            if is_pdf:
                meta = parse_pdf(
                    pdf_path=raw_path,
                    url=url,
                    url_hash=url_hash,
                    out_dir=normalized_dir,
                )
            else:
                html = raw_path.read_text(encoding="utf-8", errors="replace")
                meta = parse_html(
                    html=html,
                    url=url,
                    url_hash=url_hash,
                    out_dir=normalized_dir,
                )

            # Skip documents that produced no usable content
            if meta.get("char_count", 0) < 50:
                logger.info(f"Skipping near-empty document: {url} ({meta.get('char_count', 0)} chars)")
                continue

            records.append(meta)

        except Exception as exc:
            logger.error(f"Parser failed for {url}: {exc}", exc_info=True)

    # Write index
    normalized_index.parent.mkdir(parents=True, exist_ok=True)
    with open(normalized_index, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(f"Normalized {len(records)} documents -> {normalized_index}")
    return len(records)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run(
        raw_dir          = root / "raw",
        crawl_index      = root / "raw" / "crawl_index.jsonl",
        normalized_dir   = root / "normalized",
        normalized_index = root / "normalized" / "normalized_index.jsonl",
    )
