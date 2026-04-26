"""
crawler.py — Legal Data Pipeline Crawler
Handles static HTML, JS-rendered pages, and PDF downloads.

Design choices:
- robots.txt is checked before every domain via urllib.robotparser
- Exponential backoff (max 3 retries) on network errors / 429 / 5xx
- URL frontier is a deque; visited set keyed on normalized URL
- JS rendering is triggered when <body> text content is suspiciously thin
  relative to script tags (heuristic), or if URL is in a known JS-heavy list
- Depth is tracked per URL; hard cap at MAX_DEPTH = 3
"""

import hashlib
import json
import logging
import time
import random
import re
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
USER_AGENT = "BharatLawBot/1.0 (research; +https://github.com/example/bharat-law-pipeline)"
MAX_DEPTH = 3
CRAWL_DELAY = 2.0          # polite base delay between requests (seconds)
MAX_RETRIES = 3
BACKOFF_BASE = 2           # exponential backoff base (seconds)
REQUEST_TIMEOUT = 30       # seconds
MAX_PAGES_PER_SEED = 100    # safety cap

# Domains known to require JS rendering
JS_REQUIRED_DOMAINS = {
    "incometaxindia.gov.in",
}

# File extensions to always skip
SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".css", ".js", ".ico", ".woff", ".woff2", ".ttf",
    ".zip", ".tar", ".gz", ".mp4", ".mp3",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16]


def normalize_url(url: str) -> str:
    """Strip fragment, trailing slash, lowercase scheme+host."""
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    # Lowercase scheme and host; keep path as-is
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
    )
    return normalized.geturl().rstrip("/")


def is_pdf_url(url: str, content_type: str = "") -> bool:
    return url.lower().endswith(".pdf") or "application/pdf" in content_type


def should_skip(url: str) -> bool:
    ext = Path(urlparse(url).path).suffix.lower()
    return ext in SKIP_EXTENSIONS


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def needs_js(url: str, html: str) -> bool:
    """Heuristic: use JS rendering if domain is JS-heavy OR body text is very sparse."""
    dom = domain_of(url)
    if dom in JS_REQUIRED_DOMAINS:
        return True
    # If body text/tag ratio is below threshold, suspect JS rendering
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body
    if body:
        text_len = len(body.get_text(strip=True))
        script_count = len(body.find_all("script"))
        if text_len < 500 and script_count > 3:
            return True
    return False


# ── Robots.txt cache ─────────────────────────────────────────────────────────

class RobotsCache:
    def __init__(self):
        self._cache: dict[str, RobotFileParser] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._cache:
            rp = RobotFileParser()
            robots_url = f"{base}/robots.txt"
            try:
                rp.set_url(robots_url)
                rp.read()
            except Exception:
                # If robots.txt is unreachable, be conservative and allow
                pass
            self._cache[base] = rp
        return self._cache[base].can_fetch(USER_AGENT, url)


# ── HTTP client with retry ────────────────────────────────────────────────────

def fetch_with_retry(
    client: httpx.Client,
    url: str,
    max_retries: int = MAX_RETRIES,
) -> Optional[httpx.Response]:
    """Fetch URL with exponential backoff on failures."""
    for attempt in range(max_retries + 1):
        try:
            resp = client.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (429, 503, 502) and attempt < max_retries:
                wait = BACKOFF_BASE ** attempt + random.uniform(0, 1)
                logger.warning(f"Rate limited ({resp.status_code}) on {url}, retrying in {wait:.1f}s")
                time.sleep(wait)
                continue
            return resp
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            if attempt < max_retries:
                wait = BACKOFF_BASE ** attempt + random.uniform(0, 1)
                logger.warning(f"Network error on {url}: {exc}. Retry {attempt+1}/{max_retries} in {wait:.1f}s")
                time.sleep(wait)
            else:
                logger.error(f"Giving up on {url} after {max_retries} retries: {exc}")
                return None
    return None


# ── JS Renderer (Playwright) ──────────────────────────────────────────────────

def fetch_with_playwright(url: str) -> Optional[str]:
    """Render page with Playwright and return full HTML."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": USER_AGENT})
            page.goto(url, wait_until="networkidle", timeout=45000)
            # Wait a bit more for lazy content
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()
            return html
    except Exception as exc:
        logger.error(f"Playwright failed for {url}: {exc}")
        return None


# ── Link extractor ────────────────────────────────────────────────────────────

def extract_links(base_url: str, html: str, allowed_domains: set[str]) -> list[str]:
    """Extract and filter hrefs from HTML, restricted to allowed_domains."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full_url = urljoin(base_url, href)
        full_url = normalize_url(full_url)
        if should_skip(full_url):
            continue
        dom = domain_of(full_url)
        if dom in allowed_domains:
            links.append(full_url)
    return links


# ── Main Crawler ──────────────────────────────────────────────────────────────

class Crawler:
    def __init__(self, raw_dir: Path, index_path: Path):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = index_path
        self.robots = RobotsCache()
        self.visited: set[str] = set()
        self.index_records: list[dict] = []

    # ── Save helpers ──────────────────────────────────────────────────────────

    def _save_raw(self, url: str, content: bytes, ext: str) -> Path:
        h = url_hash(url)
        path = self.raw_dir / f"{h}{ext}"
        path.write_bytes(content)
        return path

    def _write_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            for rec in self.index_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _record(self, url: str, status: int, content_type: str, used_js: bool, path: Path):
        rec = {
            "url": url,
            "status": status,
            "content_type": content_type,
            "used_js": used_js,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path_to_raw": str(path),
        }
        self.index_records.append(rec)

    # ── Core crawl logic ──────────────────────────────────────────────────────

    def crawl(self, seed_urls: dict[str, str]) -> int:
        """
        BFS crawl from seed URLs.
        Returns total pages crawled.
        """
        # Frontier: (url, depth, seed_domain)
        frontier: deque[tuple[str, int, str]] = deque()
        
        # Determine allowed domains per seed
        seed_domains: dict[str, str] = {}
        for name, url in seed_urls.items():
            norm = normalize_url(url)
            dom = domain_of(norm)
            seed_domains[norm] = dom
            frontier.append((norm, 0, dom))

        # Per-seed page count
        domain_count: dict[str, int] = {}

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        with httpx.Client(headers=headers, follow_redirects=True) as client:
            while frontier:
                url, depth, seed_dom = frontier.popleft()

                if url in self.visited:
                    continue
                if depth > MAX_DEPTH:
                    continue
                if domain_count.get(seed_dom, 0) >= MAX_PAGES_PER_SEED:
                    continue
                if not self.robots.allowed(url):
                    logger.info(f"robots.txt disallows: {url}")
                    continue

                self.visited.add(url)

                # Polite delay
                time.sleep(CRAWL_DELAY + random.uniform(0, 0.5))

                logger.info(f"[depth={depth}] Fetching: {url}")

                # ── PDF shortcut ──────────────────────────────────────────
                if is_pdf_url(url):
                    resp = fetch_with_retry(client, url)
                    if resp and resp.status_code == 200:
                        path = self._save_raw(url, resp.content, ".pdf")
                        self._record(url, resp.status_code, "application/pdf", False, path)
                        domain_count[seed_dom] = domain_count.get(seed_dom, 0) + 1
                        logger.info(f"  Saved PDF → {path}")
                    continue

                # ── HTML fetch ────────────────────────────────────────────
                resp = fetch_with_retry(client, url)
                if resp is None or resp.status_code >= 400:
                    status = resp.status_code if resp else 0
                    logger.warning(f"  Failed ({status}): {url}")
                    continue

                content_type = resp.headers.get("content-type", "")

                # If actually a PDF despite non-.pdf URL
                if is_pdf_url(url, content_type):
                    path = self._save_raw(url, resp.content, ".pdf")
                    self._record(url, resp.status_code, "application/pdf", False, path)
                    domain_count[seed_dom] = domain_count.get(seed_dom, 0) + 1
                    continue

                html = resp.text
                used_js = False

                # ── JS rendering fallback ─────────────────────────────────
                if needs_js(url, html):
                    logger.info(f"  JS rendering for: {url}")
                    js_html = fetch_with_playwright(url)
                    if js_html:
                        html = js_html
                        used_js = True

                # Save raw HTML
                path = self._save_raw(url, html.encode("utf-8", errors="replace"), ".html")
                self._record(url, resp.status_code, content_type, used_js, path)
                domain_count[seed_dom] = domain_count.get(seed_dom, 0) + 1
                logger.info(f"  Saved HTML → {path} (JS={used_js})")

                # ── Extract child links (respect depth) ───────────────────
                if depth < MAX_DEPTH:
                    child_links = extract_links(url, html, allowed_domains={seed_dom})
                    new_links = [l for l in child_links if l not in self.visited]
                    # Prioritize PDF links and article links
                    new_links.sort(key=lambda u: (0 if is_pdf_url(u) else 1))
                    for child in new_links:
                        frontier.append((child, depth + 1, seed_dom))

        self._write_index()
        total = sum(domain_count.values())
        logger.info(f"Crawl complete. Total pages: {total}")
        return total


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    project_root = Path(__file__).resolve().parent.parent
    seed_file = project_root / "data" / "seed_urls.json"

    with open(seed_file) as f:
        seed_urls = json.load(f)

    raw_dir = project_root / "raw"
    index_path = project_root / "raw" / "crawl_index.jsonl"

    crawler = Crawler(raw_dir=raw_dir, index_path=index_path)
    count = crawler.crawl(seed_urls)
    print(f"Pages crawled: {count}")
