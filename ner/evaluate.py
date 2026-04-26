"""
ner/evaluate.py — NER Evaluation against gold_ner.jsonl

Evaluation is done at the entity level (exact span + label match).
Two modes:
  1. Strict:  text AND label must match exactly.
  2. Partial: label must match; text overlap ≥ 50% of gold span accepted.

Gold format (per line):
  {"text": "...", "entities": [{"label": ..., "text": ..., "start": ..., "end": ...}]}

The evaluator runs our NER over each gold sentence and compares predictions
to gold annotations, computing per-label and macro-averaged P/R/F1.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ner.ner_engine import extract_entities


# ── Matching helpers ──────────────────────────────────────────────────────────

def _exact_key(label: str, text: str) -> tuple:
    return (label, text.strip())


def _overlap_ratio(pred_start: int, pred_end: int, gold_start: int, gold_end: int) -> float:
    inter = max(0, min(pred_end, gold_end) - max(pred_start, gold_start))
    gold_len = gold_end - gold_start
    return inter / gold_len if gold_len > 0 else 0.0


# ── Per-label counters ────────────────────────────────────────────────────────

class LabelStats:
    def __init__(self):
        self.tp = 0
        self.fp = 0
        self.fn = 0

    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    def f1(self) -> float:
        p, r = self.precision(), self.recall()
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


# ── Main evaluation ───────────────────────────────────────────────────────────

def evaluate(gold_path: Path, strict: bool = True) -> dict:
    """
    Run NER over each gold sentence and compare to gold annotations.

    Returns a dict with per-label stats and macro averages.
    """
    stats: dict[str, LabelStats] = defaultdict(LabelStats)
    total_gold = 0
    total_pred = 0
    total_tp   = 0

    gold_records = []
    with open(gold_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                gold_records.append(json.loads(line))

    for record in gold_records:
        text         = record["text"]
        gold_ents    = record["entities"]
        pred_ents    = extract_entities(text)

        total_gold += len(gold_ents)
        total_pred += len(pred_ents)

        # Build gold set
        if strict:
            gold_set = {_exact_key(e["label"], e["text"]) for e in gold_ents}
            pred_set = {_exact_key(e.label, e.text) for e in pred_ents}

            for key in gold_set:
                label = key[0]
                if key in pred_set:
                    stats[label].tp += 1
                    total_tp += 1
                else:
                    stats[label].fn += 1

            for key in pred_set:
                label = key[0]
                if key not in gold_set:
                    stats[label].fp += 1

        else:
            # Partial match: label must match, overlap ≥ 50%
            matched_gold = set()
            for pred in pred_ents:
                matched = False
                for i, gold in enumerate(gold_ents):
                    if i in matched_gold:
                        continue
                    if pred.label != gold["label"]:
                        continue
                    ratio = _overlap_ratio(pred.start, pred.end, gold["start"], gold["end"])
                    if ratio >= 0.5:
                        stats[pred.label].tp += 1
                        total_tp += 1
                        matched_gold.add(i)
                        matched = True
                        break
                if not matched:
                    stats[pred.label].fp += 1

            for i, gold in enumerate(gold_ents):
                if i not in matched_gold:
                    stats[gold["label"]].fn += 1

    # Aggregate results
    all_labels = sorted(stats.keys())
    results = {}
    for label in all_labels:
        s = stats[label]
        results[label] = {
            "precision": round(s.precision(), 4),
            "recall":    round(s.recall(), 4),
            "f1":        round(s.f1(), 4),
            "tp":        s.tp,
            "fp":        s.fp,
            "fn":        s.fn,
        }

    # Macro average (unweighted)
    if results:
        macro_p = sum(v["precision"] for v in results.values()) / len(results)
        macro_r = sum(v["recall"]    for v in results.values()) / len(results)
        macro_f1 = sum(v["f1"]       for v in results.values()) / len(results)
    else:
        macro_p = macro_r = macro_f1 = 0.0

    # Micro average
    micro_p = total_tp / total_pred if total_pred else 0.0
    micro_r = total_tp / total_gold if total_gold else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) else 0.0

    return {
        "mode":          "strict" if strict else "partial",
        "total_gold":    total_gold,
        "total_pred":    total_pred,
        "total_tp":      total_tp,
        "per_label":     results,
        "macro": {
            "precision": round(macro_p,  4),
            "recall":    round(macro_r,  4),
            "f1":        round(macro_f1, 4),
        },
        "micro": {
            "precision": round(micro_p,  4),
            "recall":    round(micro_r,  4),
            "f1":        round(micro_f1, 4),
        },
    }


def print_report(results: dict) -> None:
    """Pretty-print evaluation report to stdout."""
    mode = results["mode"].upper()
    print(f"\n{'='*60}")
    print(f"  NER EVALUATION REPORT  ({mode} MATCH)")
    print(f"{'='*60}")
    print(f"  Gold entities : {results['total_gold']}")
    print(f"  Pred entities : {results['total_pred']}")
    print(f"  True positives: {results['total_tp']}")
    print()
    print(f"  {'Label':<28} {'P':>7} {'R':>7} {'F1':>7}  {'TP':>5} {'FP':>5} {'FN':>5}")
    print(f"  {'-'*28} {'-'*7} {'-'*7} {'-'*7}  {'-'*5} {'-'*5} {'-'*5}")
    for label, s in sorted(results["per_label"].items()):
        print(
            f"  {label:<28} {s['precision']:>7.4f} {s['recall']:>7.4f} {s['f1']:>7.4f}"
            f"  {s['tp']:>5} {s['fp']:>5} {s['fn']:>5}"
        )
    print(f"  {'-'*28} {'-'*7} {'-'*7} {'-'*7}")
    m = results["macro"]
    print(f"  {'MACRO AVG':<28} {m['precision']:>7.4f} {m['recall']:>7.4f} {m['f1']:>7.4f}")
    mi = results["micro"]
    print(f"  {'MICRO AVG':<28} {mi['precision']:>7.4f} {mi['recall']:>7.4f} {mi['f1']:>7.4f}")
    print(f"{'='*60}\n")


def run_evaluation(gold_path: Path, out_path: Path) -> dict:
    """Run both strict + partial eval, write JSON report, print to stdout."""
    strict  = evaluate(gold_path, strict=True)
    partial = evaluate(gold_path, strict=False)

    report = {"strict": strict, "partial": partial}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print_report(strict)
    print_report(partial)
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    run_evaluation(
        gold_path = root / "data"    / "gold_ner.jsonl",
        out_path  = root / "ner_out" / "evaluation_report.json",
    )
