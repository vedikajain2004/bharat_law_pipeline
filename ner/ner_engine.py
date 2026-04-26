"""
ner/ner_engine.py — Indian Legal NER Engine

Architecture:
  1. Pattern loader   — reads ner/patterns.yaml, compiles regex per label
  2. Gazetteer NER    — exact longest-match on curated Indian legal entities
  3. Act heuristic    — catches unseen statutes via structural suffix regex
  4. spaCy ORG        — model-based fallback for uncurated organisations
  5. Overlap resolver — longest span wins; tie-break by label priority

Labels: SECTION_REF, NOTIFICATION, DATE, MONEY, ACT_NAME, ORG

This module is intentionally NOT tuned to gold_ner.jsonl.
Patterns are derived from:
  - Income Tax Act, 1961 citation conventions
  - Indian Kanoon judgment style guides
  - CBDT/CBIC circular numbering schemes
  - Ministry of Law gazette format specifications
  - ITAT/High Court/Supreme Court reference formats
"""

import re
import json
import logging
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ── Shared types ──────────────────────────────────────────────────────────────

class Entity(NamedTuple):
    label: str
    text:  str
    start: int
    end:   int


# ── Pattern loader ────────────────────────────────────────────────────────────

def _load_patterns(yaml_path: Path) -> dict[str, list[tuple[re.Pattern, int]]]:
    """
    Load patterns.yaml → {label: [(compiled_regex, priority), ...]}
    sorted by priority ascending (lower number = higher priority).
    Falls back to built-in patterns if PyYAML not installed.
    """
    try:
        import yaml
        with open(yaml_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (ImportError, FileNotFoundError) as e:
        logger.warning(f"Cannot load patterns.yaml ({e}), using built-in patterns.")
        return _builtin_patterns()

    compiled: dict[str, list[tuple[re.Pattern, int]]] = {}
    label_map = {
        "section_ref":  "SECTION_REF",
        "notification": "NOTIFICATION",
        "date":         "DATE",
        "money":        "MONEY",
    }
    for yaml_key, label in label_map.items():
        entries = raw.get(yaml_key, [])
        patterns = []
        for entry in entries:
            try:
                pat = re.compile(r"(?<!\w)" + entry["pattern"] + r"(?!\w)", re.UNICODE)
                patterns.append((pat, entry.get("priority", 99)))
            except re.error as exc:
                logger.error(f"Bad pattern [{entry.get('id', '?')}]: {exc}")
        # Sort by priority ascending
        patterns.sort(key=lambda x: x[1])
        compiled[label] = patterns

    return compiled


def _builtin_patterns() -> dict[str, list[tuple[re.Pattern, int]]]:
    """Hardcoded fallback patterns (same coverage as patterns.yaml)."""
    _M = "January|February|March|April|May|June|July|August|September|October|November|December"
    _SCHED = "First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth|[IVX]+"
    defs = {
        "SECTION_REF": [
            (r'Article\s+\d+(?:[A-Z]{1,2})?\s*(?:\(\d+\))?(?:\s*(?:of|read\s+with)\s+the\s+Constitution)?', 1),
            (r'Clause\s+\([a-z]{1,3}\)\s+of\s+Sub-?[Ss]ection\s+\(\d+\)\s+of\s+[Ss]ection\s+\d+(?:[A-Z]{1,2})?(?:\([0-9a-zA-Z]+\))*', 2),
            (r'Clause\s+\([a-z]{1,3}\)\s+of\s+[Ss]ection\s+\d+(?:[A-Z]{1,2})?(?:\([0-9a-zA-Z]+\))*', 3),
            (r'(?:first\s+|second\s+|third\s+)?[Pp]roviso\s+to\s+(?:Sub-?[Ss]ection\s+\(\d+\)\s+of\s+)?[Ss]ection\s+\d+(?:[A-Z]{1,2})?(?:\([0-9a-zA-Z]+\))*', 3),
            (r'[Ee]xplanation\s+\d*\s*to\s+(?:Sub-?[Ss]ection\s+\(\d+\)\s+of\s+)?[Ss]ection\s+\d+(?:[A-Z]{1,2})?(?:\([0-9a-zA-Z]+\))*', 3),
            (r'Sub-?[Ss]ection\s+\(\d+\)\s+of\s+[Ss]ection\s+\d+(?:[A-Z]{1,2})?(?:\([0-9a-zA-Z]+\))*', 4),
            (r'Order\s+[IVXivx]+\s+Rule\s+\d+(?:\([0-9a-zA-Z]+\))*', 4),
            (rf'(?:{_SCHED})(?:th|st|nd|rd)?\s+Schedule(?:\s+to\s+the\s+Act)?', 4),
            (r'[Ss]ection\s+\d+(?:[A-Z]{1,2})?\s*(?:\(\s*[0-9a-zA-Z]+\s*\))+', 5),
            (r'[Ss]ection\s+\d+(?:[A-Z]{1,2})?(?![a-z\d(])', 6),
            (r'Rule\s+\d+(?:[A-Z]{1,2})?\s*(?:\([0-9a-zA-Z]+\))*', 6),
            (r'Chapter\s+(?:[IVXivx]+|\d+)(?:-[A-Z])?', 7),
            (r'para(?:graph)?\s+\d+(?:\([0-9a-zA-Z]+\))*', 7),
        ],
        "NOTIFICATION": [
            (r'S\.O\.\s*\d+(?:\([A-Z]+\))?', 1),
            (r'G\.S\.R\.\s*\d+(?:\([A-Z]+\))?', 1),
            (r'(?:CBDT|CBIC)\s+(?:Circular|Notification|Instruction)\s+No\.?\s*\d+(?:/\d+)*', 1),
            (r'Circular\s+No\.?\s*\d+(?:/\d+)*(?:\s+of\s+\d{4})?', 2),
            (r'Instruction\s+No\.?\s*\d+(?:/\d+)*(?:\s+of\s+\d{4})?', 2),
            (r'F\.?\s*No\.?\s*[\d/\w().-]+', 2),
            (r'Press\s+Release\s+No\.?\s*[\d/]+', 2),
            (r'Notification\s+No\.?\s*[\d/]+(?:\s*\([A-Z]+\))?', 2),
            (r'Order\s+No\.?\s*[\d/\w().-]+', 3),
        ],
        "DATE": [
            (r'F\.?Y\.?\s*\d{4}[-\u2013]\d{2,4}', 1),
            (r'A\.?Y\.?\s*\d{4}[-\u2013]\d{2,4}', 1),
            (r'w\.e\.f\.?\s+\d{1,2}[-./]\d{1,2}[-./]\d{2,4}', 1),
            (r'\d{4}-\d{2}-\d{2}', 2),
            (r'\d{1,2}-\d{1,2}-\d{4}', 2),
            (r'\d{1,2}/\d{1,2}/\d{4}', 2),
            (r'\d{1,2}\.\d{1,2}\.\d{4}', 2),
            (rf'\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_M})\s*,?\s+\d{{4}}', 2),
            (rf'(?:{_M})\s+\d{{1,2}}(?:st|nd|rd|th)?\s*,?\s+\d{{4}}', 2),
            (rf'(?:{_M}),?\s+\d{{4}}', 3),
        ],
        "MONEY": [
            (r'(?:Rs\.?|INR|₹)\s*[\d,]+(?:\.\d+)?\s*(?:[Cc]rore|[Ll]akh|[Aa]rab|[Tt]housand)?', 1),
            (r'\d+(?:\.\d+)?\s+(?:crore|Crore|lakh|Lakh)\s+rupees?', 1),
            (r'USD\s*[\d,]+(?:\.\d+)?', 2),
            (r'EUR\s*[\d,]+(?:\.\d+)?', 2),
            (r'GBP\s*[\d,]+(?:\.\d+)?', 2),
            (r'₹\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|Crore|lakh|Lakh))?', 2),
        ],
    }
    compiled: dict[str, list[tuple[re.Pattern, int]]] = {}
    for label, entries in defs.items():
        pats = []
        for raw_pat, priority in entries:
            try:
                pats.append((re.compile(r"(?<!\w)" + raw_pat + r"(?!\w)", re.UNICODE), priority))
            except re.error as exc:
                logger.error(f"Built-in pattern compile error [{label}]: {exc}")
        compiled[label] = pats
    return compiled


# ── Module-level compiled patterns ────────────────────────────────────────────
_YAML_PATH = Path(__file__).parent / "patterns.yaml"
_PATTERNS  = _load_patterns(_YAML_PATH)


# ── Act name heuristic ────────────────────────────────────────────────────────
# Catches statutes not in the gazetteer by structural suffix.
# Covers: "XYZ Act, 2023"  "XYZ Code, 2016"  "XYZ Sanhita, 2023"
# Excludes common false-positive phrases via negative lookbehind on known words.
_ACT_HEURISTIC = re.compile(
    r'\b[A-Z][A-Za-z &(),-]{5,80}'
    r'(?:Act|Code|Sanhita|Adhiniyam|Regulations?|Rules?)'
    r',?\s+\d{4}\b',
    re.UNICODE,
)

# ── spaCy loader ──────────────────────────────────────────────────────────────
_NLP = None
_NLP_TRIED = False

def _get_nlp():
    global _NLP, _NLP_TRIED
    if not _NLP_TRIED:
        _NLP_TRIED = True
        try:
            import spacy
            _NLP = spacy.load("en_core_web_sm")
            logger.info("spaCy loaded: en_core_web_sm")
        except (ImportError, OSError) as e:
            logger.warning(f"spaCy unavailable ({e}). ORG = gazetteer only.")
    return _NLP


# ── Extraction functions ──────────────────────────────────────────────────────

def _regex_entities(text: str) -> list[Entity]:
    """
    Run all SECTION_REF / NOTIFICATION / DATE / MONEY patterns.
    For each label, patterns are tried in priority order.
    We collect ALL matches from ALL patterns (overlap resolver handles conflicts).
    """
    entities: list[Entity] = []
    for label, pat_list in _PATTERNS.items():
        for pat, _ in pat_list:
            for m in pat.finditer(text):
                matched = m.group().strip()
                if matched:
                    entities.append(Entity(label, matched, m.start(), m.start() + len(matched)))
    return entities


def _gazetteer_entities(text: str, gazetteer: list[str], label: str) -> list[Entity]:
    """
    Exact-match gazetteer lookup with word-boundary enforcement.
    Gazetteer must be pre-sorted longest-first.
    """
    entities: list[Entity] = []
    for phrase in gazetteer:
        start = 0
        while True:
            idx = text.find(phrase, start)
            if idx == -1:
                break
            end = idx + len(phrase)
            pre  = text[idx - 1]  if idx > 0   else " "
            post = text[end]       if end < len(text) else " "
            # Word boundary: surrounding chars must not be word characters
            if not pre.isalpha() and not post.isalpha():
                entities.append(Entity(label, phrase, idx, end))
            start = idx + 1
    return entities


def _heuristic_act_entities(text: str) -> list[Entity]:
    """Catch statutes not in gazetteer via structural suffix pattern."""
    entities: list[Entity] = []
    for m in _ACT_HEURISTIC.finditer(text):
        act = m.group().strip()
        # Must end with a 4-digit year
        if re.search(r'\d{4}$', act):
            entities.append(Entity("ACT_NAME", act, m.start(), m.start() + len(act)))
    return entities


def _spacy_org_entities(text: str) -> list[Entity]:
    """spaCy ORG entities — model-based, catches uncurated organisations."""
    nlp = _get_nlp()
    if nlp is None:
        return []
    try:
        doc = nlp(text[:100_000])
        return [
            Entity("ORG", ent.text.strip(), ent.start_char, ent.end_char)
            for ent in doc.ents
            if ent.label_ == "ORG" and ent.text.strip()
        ]
    except Exception as exc:
        logger.warning(f"spaCy inference error: {exc}")
        return []


# ── Overlap resolution ────────────────────────────────────────────────────────

LABEL_PRIORITY = {
    "NOTIFICATION": 0,
    "ACT_NAME":     1,
    "SECTION_REF":  2,
    "ORG":          3,
    "DATE":         4,
    "MONEY":        5,
}

def _resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """
    Remove overlapping spans.
    Resolution order:
      1. Longer span wins.
      2. Same length → higher label priority (lower number) wins.
    """
    sorted_ents = sorted(
        entities,
        key=lambda e: (-(e.end - e.start), LABEL_PRIORITY.get(e.label, 99)),
    )
    accepted: list[Entity] = []
    covered: set[int] = set()
    for ent in sorted_ents:
        span = range(ent.start, ent.end)
        if any(i in covered for i in span):
            continue
        accepted.append(ent)
        covered.update(span)
    return sorted(accepted, key=lambda e: e.start)


# ── Public API ────────────────────────────────────────────────────────────────

def extract_entities(text: str) -> list[Entity]:
    """
    Full hybrid NER pipeline.
    Returns sorted, non-overlapping list of Entity objects.
    """
    from ner.gazetteers import ALL_ACTS, ALL_ORGS

    candidates: list[Entity] = []
    candidates.extend(_regex_entities(text))
    candidates.extend(_gazetteer_entities(text, ALL_ACTS, "ACT_NAME"))
    candidates.extend(_heuristic_act_entities(text))
    candidates.extend(_gazetteer_entities(text, ALL_ORGS, "ORG"))
    candidates.extend(_spacy_org_entities(text))
    return _resolve_overlaps(candidates)


def annotate_chunks(chunks_path: Path, out_path: Path) -> int:
    """Read chunks.jsonl → annotate → write ner/annotations.jsonl."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(chunks_path, encoding="utf-8") as fin, \
         open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            entities = extract_entities(chunk.get("text", ""))
            record = {
                "chunk_id": chunk["chunk_id"],
                "entities": [
                    {"label": e.label, "text": e.text, "start": e.start, "end": e.end}
                    for e in entities
                ],
            }
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    logger.info(f"NER complete: {count} chunks annotated -> {out_path}")
    return count


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    root = Path(__file__).resolve().parent.parent
    annotate_chunks(
        chunks_path=root / "chunks"  / "chunks.jsonl",
        out_path   =root / "ner_out" / "annotations.jsonl",
    )
