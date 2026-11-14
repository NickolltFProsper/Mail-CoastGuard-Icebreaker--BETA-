"""Evaluation script for Mail CoastGuard dataset.

Evaluates detection rates, false positive rates, and latency over 30 synthetic emails.
Usage:
    python evaluation/evaluate.py [--ai]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.ai_adapter import (
    SYSTEM_PROMPT,
    format_email_for_ai,
    get_ai_adapter,
    validate_ai_response,
)
from backend.config import LEVEL_RANKS
from backend.models import EmailInput
from backend.validation_engine import (
    analyze_layer1,
    analyze_layer2,
    combine_levels,
)

EVAL_EMAILS_PATH = Path(__file__).resolve().parent / "evaluation_emails.json"


def percentile(values: list[float], p: float) -> float:
    """Calculate the p-th percentile of a list of floats."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c < len(sorted_vals):
        return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])
    return sorted_vals[f]


def run_evaluation(use_ai: bool = False) -> None:
    if not EVAL_EMAILS_PATH.is_file():
        print(f"[!] Evaluation emails file not found at: {EVAL_EMAILS_PATH}")
        sys.exit(1)

    with open(EVAL_EMAILS_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    total_count = len(dataset)
    legitimate_list = [e for e in dataset if e.get("kind") == "legitimate"]
    malicious_list = [e for e in dataset if e.get("kind") == "malicious"]

    print("=" * 70)
    print("Mail CoastGuard — Evaluation Suite")
    print(f"Dataset Size: {total_count} emails ({len(legitimate_list)} legitimate, {len(malicious_list)} malicious)")
    print(f"Deep Analysis (Layer 3 AI): {'Enabled' if use_ai else 'Disabled (Layers 1 & 2 only)'}")
    print("=" * 70)

    ai_latencies: list[float] = []
    ai_errors_count = 0

    detected_malicious = 0
    strong_false_positives = 0
    total_false_positives = 0
    misclassified_items: list[dict[str, str]] = []

    adapter = get_ai_adapter() if use_ai else None

    for item in dataset:
        email_obj = EmailInput(
            sender=item.get("sender", ""),
            display_name=item.get("display_name", ""),
            reply_to=item.get("reply_to", ""),
            subject=item.get("subject", ""),
            body=item.get("body", ""),
            attachments=item.get("attachments", []),
        )

        l1 = analyze_layer1(email_obj)
        l2 = analyze_layer2(email_obj)
        l3 = None

        if use_ai and adapter:
            start_t = time.perf_counter()
            try:
                formatted = format_email_for_ai(email_obj)
                raw_response = adapter.analyze(SYSTEM_PROMPT, formatted)
                l3 = validate_ai_response(raw_response)
                elapsed = time.perf_counter() - start_t
                ai_latencies.append(elapsed)
                if l3 is None:
                    ai_errors_count += 1
            except Exception:
                ai_errors_count += 1
                ai_latencies.append(time.perf_counter() - start_t)

        final_level, _ = combine_levels(l1, l2, layer3=l3)

        kind = item.get("kind")
        item_id = item.get("id")

        if kind == "malicious":
            # Detection: YELLOW or higher
            if final_level in ("YELLOW", "RED", "BLACK"):
                detected_malicious += 1
            else:
                misclassified_items.append({
                    "id": item_id,
                    "kind": kind,
                    "final_level": final_level,
                    "reason": "False Negative (Malicious email categorized as GREEN)",
                })
        elif kind == "legitimate":
            # Strong False Positive: RED or BLACK
            if final_level in ("RED", "BLACK"):
                strong_false_positives += 1
                misclassified_items.append({
                    "id": item_id,
                    "kind": kind,
                    "final_level": final_level,
                    "reason": "Strong False Positive (Legitimate categorized as RED/BLACK)",
                })
            # Total False Positives: YELLOW or higher
            if final_level in ("YELLOW", "RED", "BLACK"):
                total_false_positives += 1

    detection_rate = (detected_malicious / len(malicious_list)) * 100 if malicious_list else 0
    strong_fp_rate = (strong_false_positives / len(legitimate_list)) * 100 if legitimate_list else 0
    total_fp_rate = (total_false_positives / len(legitimate_list)) * 100 if legitimate_list else 0

    print("\n--- Evaluation Metrics ---")
    print(f"  • Detection Rate (Target >= 90%):              {detection_rate:6.2f}%")
    print(f"  • Strong False Positives (Target <= 10%):     {strong_fp_rate:6.2f}%")
    print(f"  • Total False Positives (Informational):       {total_fp_rate:6.2f}%")

    if use_ai and ai_latencies:
        avg_lat = sum(ai_latencies) / len(ai_latencies)
        p95_lat = percentile(ai_latencies, 95)
        print(f"\n--- AI Latency & Reliability ---")
        print(f"  • Mean Latency:                               {avg_lat:6.3f} s")
        print(f"  • 95th Percentile (P95):                      {p95_lat:6.3f} s")
        print(f"  • Invalid Responses / Timeouts:               {ai_errors_count}")

    if misclassified_items:
        print("\n--- Misclassified Emails ---")
        for m in misclassified_items:
            print(f"  [{m['id']}] Level: {m['final_level']:<6} | {m['reason']}")
    else:
        print("\n[+] All emails correctly classified under configured criteria!")

    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Mail CoastGuard against synthetic emails.")
    parser.add_argument("--ai", action="store_true", help="Execute Layer 3 AI analysis as well")
    args = parser.parse_args()
    run_evaluation(use_ai=args.ai)


if __name__ == "__main__":
    main()
