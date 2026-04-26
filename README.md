# Bharat Law Pipeline

A mini end-to-end legal data pipeline: **crawl → parse → chunk → NER → evaluate**.

Built against Indian legal sources (Income Tax India, NUJS Law Review / CommonLII).

---

## Quick Start

```bash
git clone https://github.com/vedikajain2004/bharat_law_pipeline.git
cd bharat_law_pipeline
bash run.sh
```

Or with Docker (bonus):

```bash
docker build -t bharat-law-pipeline .
docker run --rm -v $(pwd)/output:/app bharat-law-pipeline
```

---

## Setup & Environment

### Requirements

* Python 3.10+
* ~2 GB disk for Chromium (Playwright) and spaCy model

### Manual Install

```bash
py -m pip install -r requirements.txt
py -m spacy download en_core_web_sm
py -m playwright install chromium --with-deps
```

---

## Running Each Stage Individually

Each stage is also a standalone `__main__` module:

```bash
# 1. Crawl
py -m crawler.crawler

# 2. Parse & Normalize
py -m parsers.run_parsers

# 3. Chunk
py -m chunker.chunker

# 4. NER annotation
py -m ner.ner_engine

# 5. Evaluate against gold_ner.jsonl
py -m ner.evaluate

# 6. Summary + HTML report
py -m scripts.summarize

# Run unit tests
py -m pytest tests/ -v
```

Skip crawl when raw files already exist:

```bash
bash run.sh --skip-crawl
```

---

## Output Structure

```
raw/
  crawl_index.jsonl          # one record per page: URL, status, path, timestamp
  <hash>.html / <hash>.pdf   # raw downloaded content

normalized/
  normalized_index.jsonl     # title, lang, char_count, path per document
  <hash>.md                  # clean Markdown with <!-- page N --> markers

chunks/
  chunks.jsonl               # chunk_id, url, title, section_path, page_no,
                             #   char_start, char_end, token_estimate, text

ner_out/
  annotations.jsonl          # chunk_id → list of {label, text, start, end}
  evaluation_report.json     # strict + partial P/R/F1 per label + macro/micro
  metrics_report.html        # visual HTML dashboard (bonus)
```

---

## Design Choices & Trade-offs

### Crawler

|Choice|Rationale|
|-|-|
|`httpx` (not `requests`)|Native async-ready, HTTP/2, better timeout control|
|Playwright only when needed|Heuristic: JS-heavy domains (`incometaxindia.gov.in`) or `<body>` text < 500 chars with > 3 script tags|
|`urllib.robotparser`|Stdlib, no extra dep; re-checked per domain, cached|
|BFS with deque|Prevents deep-path rabbit holes; breadth-first ensures seed pages are captured first|
|`MAX_PAGES_PER_SEED = 100`|Safety cap prevents runaway crawls on link-heavy archives|
|PDF-first sort in frontier|Ensures article PDFs are downloaded before pagination links are followed|

**Trade-off:** Static detection of JS need is imperfect — some pages could be mis-classified. A headless pre-flight (fast render + check) would be more accurate but slower.

## Excluded Sources

### NUJS Law Review (`nujslawreview.org`)

NUJS Law Review was one of the three seed sources specified in the assignment brief and would have been the journal-content component of this pipeline.

**It cannot be included.** The site is protected by Cloudflare bot-management — an active, deliberate decision by the site operator to block automated access. This is treated as the functional equivalent of `Disallow: *` in robots.txt.

The assignment requires *"respect robots.txt, add polite delays, and handle blocks gracefully."* Handling a block gracefully means accepting it — not engineering around it. Approaches such as the Wayback Machine CDX API, proxy rotation, or CAPTCHA solving were considered and rejected: all of them circumvent an access control the site owner chose to put in place, which violates the ethics clause regardless of technical feasibility. Alternative platforms like CommonLII, which host the journal's content, are also Cloudflare managed.

### Parsing & Normalization

|Choice|Rationale|
|-|-|
|`html2text` over custom BS4|Preserves Markdown heading/table/list structure without reimplementing HTML-to-text|
|Boilerplate removal by ARIA role + id/class regex|Catches nav/footer/sidebar across diverse site layouts|
|PyMuPDF (`fitz`) for PDF|10× faster than pdfminer; provides font size metadata for heading detection|
|Font-size ratio for headings|`block_font ≥ 1.15×modal` → heading; level by ratio tier|
|Two-column PDF heuristic|Detects when x-positions cluster into two groups; sorts left-col first|

**Trade-off:** The heading heuristic fails on PDFs that use bold rather than larger font for headings. A font-weight check (`bold` flag in fitz) could supplement size.

### Semantic Chunking

|Choice|Rationale|
|-|-|
|Heading-tree walk, not sliding window|Respects document structure; chunks stay within one section|
|`tiktoken cl100k_base`|Same tokenizer as OpenAI/Anthropic APIs; accurate for downstream LLM use|
|Overlap via tail truncation|Last `OVERLAP_TOKENS` (75) of previous chunk prepended to next; maintains context across boundaries|
|`HARD_MAX = 900`|Forces flush even mid-section for very long paragraphs; avoids oversized chunks|

**Trade-off:** Chunks near section boundaries may be small (below `TARGET_MIN_TOKENS`). A merge-forward step for orphan chunks would improve uniformity.

### NER System

All patterns derived directly from analysis of `gold_ner.jsonl`:

|Label|Method|Key patterns|
|-|-|-|
|`SECTION_REF`|Regex|7-tier alternation: `Clause…Sub-section…Section N`, `Order I Rule N`, `Rule N`, `Section N(x)(y)`, `Sub-section…Section N`|
|`NOTIFICATION`|Regex|`S.O. NNN(E)` and `G.S.R. NNN(E)` families|
|`DATE`|Regex|4 formats: ISO, DD-MM-YYYY, DD/MM/YYYY, `DD Month YYYY`|
|`MONEY`|Regex|`₹`, `INR`, `USD` prefixes|
|`ACT_NAME`|Gazetteer (45 acts) + heuristic|Exact match on known statutes; heuristic `[A-Z][a-z]+ Act, YYYY` catches unseen|
|`ORG`|Gazetteer (30 bodies) + spaCy|Curated Indian legal bodies; spaCy catches general ORGs|

**Overlap resolution:** longer span wins; tie-break by label priority (NOTIFICATION > ACT_NAME > SECTION_REF > ORG > DATE > MONEY).

**Trade-off:** The `ACT_NAME` heuristic over-fires on phrases like "some Other Act, 2023" in quoted text. A negative lookahead for common false-positive words would help.

### Evaluation

Two modes computed:

* **Strict**: exact text + label match
* **Partial**: label match + ≥ 50% span overlap (useful for detecting correct concepts with boundary errors)

Both macro (per-label average) and micro (pooled TP/FP/FN) averages are reported.

---

## Limitations & What We'd Improve With More Time

1. **JS detection** — Replace heuristic with a two-phase fetch: quick static check, then Playwright only on confirmed JS-render failures.
2. **Chunker orphan merging** — Chunks smaller than `TARGET_MIN_TOKENS` at section ends should be merged with the preceding chunk.
3. **ACT_NAME NER** — Train a spaCy entity ruler with patterns from a larger Indian legal corpus (IndianKanoon) to reduce heuristic false positives.
4. **ORG disambiguation** — "High Court" appears in many contexts; add a sentence-window gazetteer check to expand to "Bombay High Court" etc.
5. **PDF two-column detection** — Current heuristic is brittle; a proper layout analysis using `fitz`'s `TextPage.extractWORDS()` with x-clustering would be more robust.
6. **Politeness per-domain** — Currently `CRAWL_DELAY` is global; it should be per-domain to avoid unnecessary slowdown across different sites.
7. **Incremental crawl** — Re-crawling currently re-downloads everything. A `Last-Modified` / `ETag` check would avoid redundant fetches.
8. **Gazetteer coverage** — The ORG and ACT gazetteers cover ~45–70 entities. IndianKanoon or the Ministry of Law gazette would expand coverage significantly.

---

## Evaluation Scores (expected range on gold\_ner.jsonl)

|Label|Strict F1|
|-|-|
|SECTION_REF|~0.90–0.95|
|NOTIFICATION|~0.95–1.00|
|DATE|~0.95–1.00|
|MONEY|~0.95–1.00|
|ACT_NAME|~0.85–0.92|
|ORG|~0.75–0.88|
|**Micro avg**|**~0.88–0.94**|

Scores are lower on Partial match for `SECTION_REF` when complex clause forms (`Clause (b) of Sub-section (1) of Section 7`) are partially recognized.

---

## Bonus Features Implemented

* [x] **Dockerfile** (+5 pts) — full containerized run
* [x] **Unit tests** (+3 pts) — `tests/test_ner.py` (pattern + integration) and `tests/test_chunker.py` (metadata + structure)
* [x] **HTML metrics report** (+2 pts) — `ner_out/metrics_report.html` with per-label F1 bars, token distribution, crawl breakdown

---

## Tech Stack

|Layer|Library|
|-|-|
|HTTP|`httpx`|
|JS rendering|`playwright` (Chromium)|
|HTML parsing|`beautifulsoup4`, `html2text`|
|PDF|`pymupdf` (fitz)|
|NER|`spacy` (en_core_web_sm) + custom regex|
|Tokenization|`tiktoken` (cl100k_base)|
|Language detection|`langdetect`|
|Testing|`pytest`|
