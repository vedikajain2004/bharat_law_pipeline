#!/usr/bin/env bash
# run.sh — One-command pipeline: install → crawl → parse → chunk → NER → eval → summary
# Usage: bash run.sh [--skip-crawl] [--skip-install]
set -euo pipefail

SKIP_INSTALL=false
SKIP_CRAWL=false

for arg in "$@"; do
  case $arg in
    --skip-install) SKIP_INSTALL=true ;;
    --skip-crawl)   SKIP_CRAWL=true   ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       BHARAT LAW PIPELINE — FULL RUN                    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Dependencies ───────────────────────────────────────────────────────────
if [ "$SKIP_INSTALL" = false ]; then
  echo "▶  [1/6] Installing Python dependencies…"
  py -m pip install --quiet -r requirements.txt
  echo "▶  [1/6] Downloading spaCy model…"
  py -m spacy download en_core_web_sm --quiet || true
  echo "▶  [1/6] Installing Playwright browsers…"
  py -m playwright install chromium --with-deps || true
  echo "✓  Dependencies ready."
else
  echo "–  [1/6] Skipping install (--skip-install)"
fi
echo ""

# ── 2. Crawl ──────────────────────────────────────────────────────────────────
if [ "$SKIP_CRAWL" = false ]; then
  echo "▶  [2/6] Crawling seed URLs…"
  mkdir -p raw
  py -m crawler.crawler
  echo "✓  Crawl complete."
else
  echo "–  [2/6] Skipping crawl (--skip-crawl). Using existing raw/ files."
fi
echo ""

# ── 3. Parse & Normalize ──────────────────────────────────────────────────────
echo "▶  [3/6] Parsing & normalizing HTML/PDF…"
mkdir -p normalized
py -m parsers.run_parsers
echo "✓  Parsing complete."
echo ""

# ── 4. Chunk ──────────────────────────────────────────────────────────────────
echo "▶  [4/6] Chunking normalized documents…"
mkdir -p chunks
py -m chunker.chunker
echo "✓  Chunking complete."
echo ""

# ── 5. NER ────────────────────────────────────────────────────────────────────
echo "▶  [5/6] Running NER on all chunks…"
mkdir -p ner_out
py -m ner.ner_engine
echo "✓  NER complete."
echo ""

# ── 5b. Evaluate NER ──────────────────────────────────────────────────────────
echo "▶  [5b]  Evaluating NER against gold_ner.jsonl…"
py -m ner.evaluate
echo "✓  Evaluation complete. Report → ner_out/evaluation_report.json"
echo ""

# ── 6. Summary ────────────────────────────────────────────────────────────────
echo "▶  [6/6] Generating final summary…"
py -m scripts.summarize
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  All stages complete. Outputs:                           ║"
echo "║    raw/              → crawled content                   ║"
echo "║    normalized/       → clean markdown                    ║"
echo "║    chunks/           → semantic chunks                   ║"
echo "║    ner_out/          → annotations + evaluation report   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
