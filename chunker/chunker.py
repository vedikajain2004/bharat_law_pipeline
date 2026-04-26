"""
chunker/chunker.py — Semantic Chunker

Strategy:
1. Parse the Markdown into a tree of sections using heading levels.
2. Walk the tree; accumulate paragraphs until we exceed TARGET_MAX_TOKENS.
3. When a chunk fills up, slide a window of OVERLAP_TOKENS forward
   (keeping the last N tokens of the previous chunk as context prefix).
4. Page numbers are tracked via <!-- page N --> markers injected by the PDF parser.
5. char_start / char_end are absolute offsets into the *normalized* document text.

Token estimation: tiktoken (cl100k_base) with word-count fallback.
Target: 400–800 tokens, overlap: 50–100 tokens.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_MIN_TOKENS  = 400
TARGET_MAX_TOKENS  = 800
OVERLAP_TOKENS     = 75        # ~halfway through 50–100 range
HARD_MAX_TOKENS    = 900       # safety valve before forced split

# ── Token counter ─────────────────────────────────────────────────────────────
# Lazy init: tiktoken downloads a BPE file on first use; skip if network unavailable.
_tiktoken_enc = None
_tiktoken_available = None   # None = not yet tried

def _get_tiktoken_enc():
    global _tiktoken_enc, _tiktoken_available
    if _tiktoken_available is None:
        try:
            import tiktoken
            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
            _tiktoken_available = True
        except Exception:
            _tiktoken_available = False
            logger.warning("tiktoken unavailable — using word-count approximation")
    return _tiktoken_enc if _tiktoken_available else None

def count_tokens(text: str) -> int:
    enc = _get_tiktoken_enc()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, int(len(text.split()) / 0.75))

def truncate_to_tokens(text: str, n: int) -> str:
    enc = _get_tiktoken_enc()
    if enc is not None:
        tokens = enc.encode(text)
        return enc.decode(tokens[-n:]) if len(tokens) > n else text
    words = text.split()
    keep = int(n * 0.75)
    return " ".join(words[-keep:]) if len(words) > keep else text


# ── Section tree ──────────────────────────────────────────────────────────────

PAGE_MARKER_RE  = re.compile(r"<!--\s*page\s+(\d+)\s*-->")
HEADING_RE      = re.compile(r"^(#{1,4})\s+(.+)$")
PARAGRAPH_RE    = re.compile(r"\n{2,}")


@dataclass
class Block:
    """Leaf content block: a paragraph or list item."""
    text: str
    page_no: int
    char_start: int    # offset in full document string
    char_end:   int


@dataclass
class Section:
    heading:    str
    level:      int            # 1–4 (0 = document root)
    blocks:     list[Block]    = field(default_factory=list)
    children:   list["Section"] = field(default_factory=list)

    @property
    def path(self) -> list[str]:
        return [self.heading] if self.heading else []


def _parse_sections(text: str) -> Section:
    """Parse a Markdown string into a Section tree, tracking page numbers."""
    root = Section(heading="", level=0)
    stack: list[Section] = [root]
    current_page = 1
    pos = 0

    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        line_start = pos
        pos += len(raw_line)

        # Page marker
        pm = PAGE_MARKER_RE.match(line.strip())
        if pm:
            current_page = int(pm.group(1))
            continue

        # Heading
        hm = HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            heading_text = hm.group(2).strip()
            new_sec = Section(heading=heading_text, level=level)
            # Pop stack until we find a parent of higher (lower number) level
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            stack[-1].children.append(new_sec)
            stack.append(new_sec)
            continue

        # Content line — attach to current section
        stripped = line.strip()
        if stripped:
            current_sec = stack[-1]
            current_sec.blocks.append(Block(
                text=stripped,
                page_no=current_page,
                char_start=line_start,
                char_end=line_start + len(line),
            ))

    return root


def _section_path(section: Section, ancestors: list[Section]) -> list[str]:
    """Build breadcrumb path from root to current section."""
    path = []
    for anc in ancestors:
        if anc.heading:
            path.append(anc.heading)
    if section.heading:
        path.append(section.heading)
    return path


# ── Chunk builder ─────────────────────────────────────────────────────────────

@dataclass
class ChunkCandidate:
    texts:      list[str]
    pages:      list[int]
    char_starts: list[int]
    char_ends:   list[int]
    section_path: list[str]

    def token_count(self) -> int:
        return count_tokens(" ".join(self.texts))

    def merged_text(self) -> str:
        return " ".join(self.texts)

    def page_no(self) -> int:
        return self.pages[0] if self.pages else 1

    def char_start(self) -> int:
        return self.char_starts[0] if self.char_starts else 0

    def char_end(self) -> int:
        return self.char_ends[-1] if self.char_ends else 0


def _iter_blocks(section: Section, ancestors: list[Section]) -> Iterator[tuple[Block, list[str]]]:
    """Depth-first iteration over all blocks with their section path."""
    path = _section_path(section, ancestors)
    for block in section.blocks:
        yield block, path
    for child in section.children:
        yield from _iter_blocks(child, ancestors + [section])


def _build_chunks(
    root: Section,
    url: str,
    url_hash: str,
    title: str,
    overlap_prefix: str = "",
) -> list[dict]:
    chunks: list[dict] = []
    candidate = ChunkCandidate(texts=[], pages=[], char_starts=[], char_ends=[], section_path=[])

    if overlap_prefix:
        candidate.texts.append(overlap_prefix)

    chunk_counter = 0

    def flush(candidate: ChunkCandidate, force: bool = False) -> ChunkCandidate:
        nonlocal chunk_counter
        text = candidate.merged_text().strip()
        if not text:
            return ChunkCandidate(texts=[], pages=[], char_starts=[], char_ends=[], section_path=[])

        tokens = count_tokens(text)
        if tokens < TARGET_MIN_TOKENS and not force:
            return candidate

        chunk_counter += 1
        chunk_id = f"{url_hash}:{chunk_counter:04d}"
        chunks.append({
            "chunk_id":     chunk_id,
            "url":          url,
            "title":        title,
            "section_path": candidate.section_path,
            "page_no":      candidate.page_no(),
            "char_start":   candidate.char_start(),
            "char_end":     candidate.char_end(),
            "token_estimate": tokens,
            "text":         text,
        })

        # Build overlap prefix for next chunk
        new_prefix = truncate_to_tokens(text, OVERLAP_TOKENS)
        new_cand = ChunkCandidate(
            texts=[new_prefix],
            pages=candidate.pages[-1:],
            char_starts=candidate.char_starts[-1:],
            char_ends=candidate.char_ends[-1:],
            section_path=candidate.section_path,
        )
        return new_cand

    for block, section_path in _iter_blocks(root, []):
        # When section path changes, flush current chunk
        if section_path != candidate.section_path and candidate.texts:
            candidate = flush(candidate, force=False)

        candidate.section_path = section_path
        candidate.texts.append(block.text)
        candidate.pages.append(block.page_no)
        candidate.char_starts.append(block.char_start)
        candidate.char_ends.append(block.char_end)

        # Force flush if over hard max
        if candidate.token_count() >= HARD_MAX_TOKENS:
            candidate = flush(candidate, force=True)

    # Flush remainder
    if len(candidate.texts) > (1 if overlap_prefix else 0):
        flush(candidate, force=True)

    return chunks


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_document(
    md_text: str,
    url: str,
    url_hash: str,
    title: str,
) -> list[dict]:
    """Chunk a normalized Markdown document. Returns list of chunk dicts."""
    root = _parse_sections(md_text)
    return _build_chunks(root, url, url_hash, title)


def run(
    normalized_index: Path,
    chunks_dir: Path,
) -> tuple[int, float]:
    """
    Process all normalized documents and write chunks/chunks.jsonl.
    Returns (total_chunks, avg_tokens).
    """
    import json

    chunks_dir.mkdir(parents=True, exist_ok=True)
    out_path = chunks_dir / "chunks.jsonl"

    all_chunks: list[dict] = []

    with open(normalized_index, encoding="utf-8") as f:
        norm_records = [json.loads(line) for line in f if line.strip()]

    for rec in norm_records:
        md_path = Path(rec["path_to_text"])
        if not md_path.exists():
            logger.warning(f"Missing normalized file: {md_path}")
            continue

        md_text = md_path.read_text(encoding="utf-8")
        chunks = chunk_document(
            md_text  = md_text,
            url      = rec["url"],
            url_hash = rec["url_hash"],
            title    = rec.get("title", ""),
        )
        all_chunks.extend(chunks)
        logger.info(f"Chunked '{rec['title']}' → {len(chunks)} chunks")

    # Write output
    with open(out_path, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    total = len(all_chunks)
    avg   = sum(c["token_estimate"] for c in all_chunks) / total if total else 0
    logger.info(f"Chunking done: {total} chunks, avg {avg:.0f} tokens")
    return total, avg


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    run(
        normalized_index = root / "normalized" / "normalized_index.jsonl",
        chunks_dir       = root / "chunks",
    )
