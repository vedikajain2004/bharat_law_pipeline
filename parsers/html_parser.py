"""
parsers/html_parser.py — HTML -> Markdown normalizer

Design choices:
- Uses html2text for faithful heading/list/table conversion
- Strips boilerplate: navbars, footers, cookie banners, sidebars
  (identified by common CSS class/id heuristics and aria-roles)
- Extracts <title> or <h1> as document title
- langdetect used for language detection (falls back to "en")
- Outputs GitHub-flavoured Markdown suitable for downstream chunking

Robustness notes:
- _remove_junk collects ALL candidates first, skips any whose ancestor
  is already marked, then decomposes only top-level roots — avoids the
  "decompose a parent then hit its children again" crash on JS-heavy SPAs.
- html2text is wrapped in try/except; falls back to soup.get_text() so
  near-empty SPA shells still produce a usable (if minimal) document.
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import html2text
from bs4 import BeautifulSoup, Comment, Tag

logger = logging.getLogger(__name__)

# ── Boilerplate selectors ─────────────────────────────────────────────────────
JUNK_ROLES = {"navigation", "banner", "contentinfo", "search", "complementary"}
JUNK_TAGS  = {"nav", "footer", "header", "aside", "script", "style",
               "noscript", "iframe", "form", "button"}
JUNK_ID_RE = re.compile(
    r"\b(nav|navbar|footer|header|sidebar|cookie|banner|menu|breadcrumb|"
    r"skip|search|ad-|ads-|advertisement|promo|share|social)\b",
    re.I,
)

# ── html2text config ──────────────────────────────────────────────────────────
def _make_converter() -> html2text.HTML2Text:
    h = html2text.HTML2Text()
    h.ignore_links       = False
    h.ignore_images      = True
    h.ignore_tables      = False
    h.body_width         = 0
    h.protect_links      = False
    h.unicode_snob       = True
    h.wrap_links         = False
    h.mark_code          = True
    h.single_line_break  = False
    h.ul_item_mark       = "-"
    return h

_CONVERTER = _make_converter()


# ── Language detection ────────────────────────────────────────────────────────
def _detect_language(text: str) -> str:
    try:
        from langdetect import detect
        sample = text[:2000].strip()
        if len(sample) > 20:
            return detect(sample)
    except Exception:
        pass
    return "en"


# ── Safe tag check ────────────────────────────────────────────────────────────
def _is_alive(tag) -> bool:
    """Return False if the tag has already been decomposed (its __dict__ was cleared)."""
    try:
        # After decompose(), __dict__ is cleared; accessing .name raises AttributeError
        _ = tag.name
        return True
    except AttributeError:
        return False


# ── Core cleaning ─────────────────────────────────────────────────────────────
def _remove_junk(soup: BeautifulSoup) -> None:
    """
    Remove boilerplate elements in-place.

    Strategy: collect ALL candidates into one set, then skip any candidate
    whose ancestor is already in the set (avoids double-decompose on children
    of a parent we already removed, which crashes on JS-rendered SPA pages).
    """
    # Remove HTML comments first — these are NavigableString, safe to do separately
    for c in list(soup.find_all(string=lambda t: isinstance(t, Comment))):
        try:
            c.extract()
        except Exception:
            pass

    # Collect all candidate tags across all criteria
    candidates: list[Tag] = []

    for tag in soup.find_all(True):
        if not isinstance(tag, Tag) or not _is_alive(tag):
            continue
        try:
            name = (tag.name or "").lower()
            role = (tag.get("role") or "").lower()
            tag_id    = tag.get("id", "") or ""
            tag_class = tag.get("class", "") or []
            class_str = " ".join(tag_class) if isinstance(tag_class, list) else str(tag_class)
            attrs_str = f"{tag_id} {class_str}"
        except AttributeError:
            # Tag was decomposed by a previous iteration step — skip it
            continue

        if (name in JUNK_TAGS
                or role in JUNK_ROLES
                or JUNK_ID_RE.search(attrs_str)):
            candidates.append(tag)

    # Keep only root-level candidates (skip descendants of already-selected ancestors)
    # Build a set of id() for fast ancestor lookup
    candidate_ids = {id(t) for t in candidates}
    roots: list[Tag] = []
    for tag in candidates:
        if not _is_alive(tag):
            continue
        # Walk up the parent chain; if any ancestor is also a candidate, skip this tag
        parent = tag.parent
        is_descendant = False
        while parent is not None:
            try:
                if id(parent) in candidate_ids:
                    is_descendant = True
                    break
                parent = parent.parent
            except AttributeError:
                break
        if not is_descendant:
            roots.append(tag)

    # Now decompose only the roots — BeautifulSoup will handle their subtrees
    for tag in roots:
        try:
            if _is_alive(tag):
                tag.decompose()
        except Exception:
            pass


def _extract_title(soup: BeautifulSoup, url: str) -> str:
    """Extract best available title."""
    try:
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            title = re.sub(r"\s*[|\-\u2013\u2014]\s*.{3,40}$", "", title).strip()
            if title:
                return title
    except Exception:
        pass
    try:
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
    except Exception:
        pass
    return urlparse(url).path.strip("/").replace("-", " ").replace("/", " > ").title() or url


def _html_to_markdown(html_str: str) -> str:
    """
    Convert HTML string to Markdown.
    Falls back to plain text extraction if html2text raises.
    """
    try:
        return _CONVERTER.handle(html_str)
    except Exception as exc:
        logger.debug(f"html2text failed ({exc}), falling back to get_text")
        # Parse again to extract text safely
        soup = BeautifulSoup(html_str, "html.parser")
        return soup.get_text(separator="\n", strip=True)


def _clean_markdown(md: str) -> str:
    """Post-process the markdown output."""
    md = re.sub(r"\n{3,}", "\n\n", md)
    # Remove pure link-only lines (navigation residue)
    md = re.sub(r"^\s*\[([^\]]{1,60})\]\([^)]+\)\s*$", "", md, flags=re.M)
    md = "\n".join(line.rstrip() for line in md.splitlines())
    return md.strip()


# ── Public API ────────────────────────────────────────────────────────────────
def parse_html(
    html: str,
    url: str,
    url_hash: Optional[str] = None,
    out_dir: Optional[Path] = None,
) -> dict:
    """
    Parse raw HTML into clean Markdown.

    Returns a metadata dict (suitable for normalized_index.jsonl).
    If out_dir is provided, writes the markdown file there.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract title BEFORE stripping junk (title tag lives in <head>)
    title = _extract_title(soup, url)

    _remove_junk(soup)

    # Find main content area — try progressively broader selectors
    main = (
        soup.find("main")
        or soup.find(id=re.compile(r"content|main", re.I))
        or soup.find(class_=re.compile(r"content|article|post|entry", re.I))
        or soup.body
        or soup
    )

    md = _clean_markdown(_html_to_markdown(str(main)))

    # If we got almost nothing (JS SPA that Playwright didn't hydrate fully),
    # try the whole soup as a last resort
    if len(md) < 200 and main is not soup:
        md_full = _clean_markdown(_html_to_markdown(str(soup)))
        if len(md_full) > len(md):
            md = md_full

    lang = _detect_language(md)

    if url_hash is None:
        url_hash = hashlib.md5(url.encode()).hexdigest()[:16]

    record = {
        "url":               url,
        "url_hash":          url_hash,
        "source_type":       "html",
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
        logger.info(f"HTML parsed -> {md_path}  ({len(md):,} chars, lang={lang})")

    return record
