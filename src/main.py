#!/usr/bin/env python3
"""
Pre-Approval Website-Verification Tool — CLI Entry Point

Usage:
    python -m src.main samples/Sample-01---Community-Class-GallopNYC.pdf
    python -m src.main samples/Sample-01---Community-Class-GallopNYC.pdf --output my_report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser.parser import PDFParser
from src.gatherer.gatherer import WebGatherer
from src.reporter.generator import ReportGenerator


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pre-Approval Website-Verification Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main samples/Sample-01---Community-Class-GallopNYC.pdf
  python -m src.main samples/Sample-03---Coaching-92NY-Parenting.pdf --output my_report
  python -m src.main samples/Sample-02---Community-Class-Gracie-Barra-Jiu-Jitsu.pdf --json
        """,
    )
    p.add_argument("pdf", help="Path to the pre-approval application PDF")
    p.add_argument(
        "-o",
        "--output",
        help="Custom output filename stem (without extension) for the HTML report",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON to stdout instead of generating HTML",
    )
    p.add_argument(
        "--no-report",
        action="store_true",
        help="Skip HTML report generation (only run parse + gather)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Navigation timeout in seconds (default: 30)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    print(f"Processing: {pdf_path.name}")
    print("-" * 60)

    # ── Step 1: Parse ──────────────────────────────────────────────
    print("Step 1/3: Parsing PDF...")
    try:
        app_data = PDFParser(str(pdf_path)).parse()
    except Exception as e:
        print(f"  ✗ Parse failed: {e}", file=sys.stderr)
        return 1
    print(f"  [OK] Parsed as: {app_data.get('form_type', 'unknown')}")

    # ── Step 2: Gather ─────────────────────────────────────────────
    print("Step 2/3: Verifying on provider website...")
    gatherer = WebGatherer()
    try:
        evidence = gatherer.gather(app_data)
    except Exception as e:
        print(f"  ✗ Gather failed: {e}", file=sys.stderr)
        return 1

    item_status = evidence.get("item", {}).get("status", "?")
    amount_status = evidence.get("amount", {}).get("status", "?")
    print(f"  [OK] Item: {item_status} | Amount: {amount_status} | Overall: {evidence.get('overall_status')}")

    if args.json:
        print(json.dumps(evidence, indent=2))
        return 0

    # ── Step 3: Report ─────────────────────────────────────────────
    if not args.no_report:
        print("Step 3/3: Generating HTML report...")
        try:
            generator = ReportGenerator()
            report_path = generator.generate(
                application=app_data,
                verification={"item": evidence["item"], "amount": evidence["amount"]},
                evidence=evidence,
                output_name=args.output,
            )
            print(f"  [OK] Report saved: {report_path}")
        except Exception as e:
            print(f"  ✗ Report generation failed: {e}", file=sys.stderr)
            return 1
    else:
        print("Step 3/3: Skipped (--no-report)")

    print("-" * 60)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())