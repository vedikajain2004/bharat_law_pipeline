"""
scripts/summarize.py — Final Pipeline Summary + HTML Metrics Report

Reads all index/output files and prints the required summary line:
  Pages crawled: N
  Chunks created: N
  Avg tokens/chunk: N
  NER F1-score: N

Also generates ner_out/metrics_report.html for the bonus +2 pts.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def main():
    # ── Collect stats ─────────────────────────────────────────────────────────
    crawl_index = load_jsonl(ROOT / "raw" / "crawl_index.jsonl")
    pages_crawled = len(crawl_index)

    chunks = load_jsonl(ROOT / "chunks" / "chunks.jsonl")
    total_chunks = len(chunks)
    avg_tokens = (
        sum(c.get("token_estimate", 0) for c in chunks) / total_chunks
        if total_chunks else 0
    )

    # NER F1
    eval_report_path = ROOT / "ner_out" / "evaluation_report.json"
    ner_f1 = "N/A (run evaluate.py)"
    per_label = {}
    if eval_report_path.exists():
        with open(eval_report_path) as f:
            report = json.load(f)
        ner_f1 = report.get("strict", {}).get("micro", {}).get("f1", "N/A")
        per_label = report.get("strict", {}).get("per_label", {})

    # ── Console summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("  BHARAT LAW PIPELINE — FINAL SUMMARY")
    print("=" * 50)
    print(f"  Pages crawled:      {pages_crawled}")
    print(f"  Chunks created:     {total_chunks}")
    print(f"  Avg tokens/chunk:   {avg_tokens:.0f}")
    print(f"  NER F1-score:       {ner_f1}")
    print("=" * 50 + "\n")

    # ── HTML report ───────────────────────────────────────────────────────────
    _write_html_report(
        pages_crawled, total_chunks, avg_tokens, ner_f1,
        per_label, chunks, crawl_index
    )


def _bar(value: float, max_val: float = 1.0, width: int = 200) -> str:
    pct = min(value / max_val, 1.0) * 100
    filled = int(pct * width / 100)
    color = "#22c55e" if pct >= 70 else "#f59e0b" if pct >= 40 else "#ef4444"
    return (
        f'<div style="background:#e5e7eb;border-radius:4px;height:18px;width:{width}px;display:inline-block;">'
        f'<div style="background:{color};width:{filled}px;height:100%;border-radius:4px;"></div></div>'
        f'<span style="margin-left:8px;font-weight:600;">{pct:.1f}%</span>'
    )


def _write_html_report(pages, chunks_n, avg_tok, f1, per_label, chunks, crawl):
    # Token distribution
    token_bins = {"< 400": 0, "400–600": 0, "600–800": 0, "> 800": 0}
    for c in chunks:
        t = c.get("token_estimate", 0)
        if   t < 400:  token_bins["< 400"] += 1
        elif t < 600:  token_bins["400–600"] += 1
        elif t <= 800: token_bins["600–800"] += 1
        else:          token_bins["> 800"] += 1

    # Source type breakdown
    html_count = sum(1 for r in crawl if r.get("path_to_raw", "").endswith(".html"))
    pdf_count  = sum(1 for r in crawl if r.get("path_to_raw", "").endswith(".pdf"))
    js_count   = sum(1 for r in crawl if r.get("used_js", False))

    label_rows = ""
    for label, s in sorted(per_label.items()):
        p, r, f = s["precision"], s["recall"], s["f1"]
        label_rows += f"""
        <tr>
          <td><code>{label}</code></td>
          <td>{p:.4f}</td><td>{r:.4f}</td>
          <td><strong>{f:.4f}</strong></td>
          <td>{s['tp']}</td><td>{s['fp']}</td><td>{s['fn']}</td>
          <td>{_bar(f)}</td>
        </tr>"""

    token_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td><td>{v/chunks_n*100:.1f}%</td></tr>"
        for k, v in token_bins.items()
    ) if chunks_n else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Bharat Law Pipeline — Metrics Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 40px; color: #1f2937; background: #f9fafb; }}
  h1   {{ color: #1d4ed8; }} h2 {{ color: #1e40af; margin-top: 2em; border-bottom: 2px solid #bfdbfe; padding-bottom: .3em; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
  th   {{ background: #1d4ed8; color: #fff; padding: 10px 14px; text-align: left; }}
  td   {{ padding: 9px 14px; border-bottom: 1px solid #e5e7eb; }}
  tr:last-child td {{ border: none; }}
  .stat-grid {{ display: flex; gap: 20px; flex-wrap: wrap; margin: 1em 0; }}
  .stat-card {{ background: #fff; border-radius: 10px; padding: 20px 28px; box-shadow: 0 1px 4px rgba(0,0,0,.1); min-width: 160px; }}
  .stat-card .val {{ font-size: 2em; font-weight: 700; color: #1d4ed8; }}
  .stat-card .lbl {{ color: #6b7280; font-size: .9em; margin-top: 4px; }}
  code {{ background: #eff6ff; padding: 2px 6px; border-radius: 3px; font-size: .9em; color: #1d4ed8; }}
</style>
</head>
<body>
<h1>🏛️ Bharat Law Pipeline — Metrics Report</h1>

<h2>Pipeline Summary</h2>
<div class="stat-grid">
  <div class="stat-card"><div class="val">{pages}</div><div class="lbl">Pages Crawled</div></div>
  <div class="stat-card"><div class="val">{html_count}</div><div class="lbl">HTML Pages</div></div>
  <div class="stat-card"><div class="val">{pdf_count}</div><div class="lbl">PDFs</div></div>
  <div class="stat-card"><div class="val">{js_count}</div><div class="lbl">JS-Rendered</div></div>
  <div class="stat-card"><div class="val">{chunks_n}</div><div class="lbl">Chunks</div></div>
  <div class="stat-card"><div class="val">{avg_tok:.0f}</div><div class="lbl">Avg Tokens/Chunk</div></div>
  <div class="stat-card"><div class="val">{f1 if isinstance(f1, str) else f"{f1:.4f}"}</div><div class="lbl">NER Micro F1</div></div>
</div>

<h2>NER Performance (Strict — per label)</h2>
<table>
  <thead>
    <tr><th>Label</th><th>Precision</th><th>Recall</th><th>F1</th><th>TP</th><th>FP</th><th>FN</th><th>F1 Bar</th></tr>
  </thead>
  <tbody>{label_rows}</tbody>
</table>

<h2>Chunk Token Distribution</h2>
<table>
  <thead><tr><th>Token Range</th><th>Count</th><th>% of Total</th></tr></thead>
  <tbody>{token_rows}</tbody>
</table>

<h2>Crawl Composition</h2>
<table>
  <thead><tr><th>Type</th><th>Count</th></tr></thead>
  <tbody>
    <tr><td>HTML (static)</td><td>{html_count - js_count}</td></tr>
    <tr><td>HTML (JS-rendered)</td><td>{js_count}</td></tr>
    <tr><td>PDF</td><td>{pdf_count}</td></tr>
  </tbody>
</table>

<p style="margin-top:3em;color:#9ca3af;font-size:.85em;">Generated by Bharat Law Pipeline · bharat_law_pipeline/scripts/summarize.py</p>
</body>
</html>"""

    out_path = ROOT / "ner_out" / "metrics_report.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"  HTML report: {out_path}")


if __name__ == "__main__":
    main()
