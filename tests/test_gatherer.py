"""
End-to-end test: runs the PDFParser on all samples, feeds each to
the WebGatherer, captures date-stamped screenshots, and prints
verification summaries.

Usage:
    python tests/test_gatherer.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser.parser import PDFParser
from src.gatherer.gatherer import WebGatherer


def safe(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def run_test(pdf_path: Path, label: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {label}")
    print(f"{'=' * 72}")

    # Step 1: Parse
    try:
        form_data = PDFParser(str(pdf_path)).parse()
    except Exception as e:
        print(f"  PARSE ERROR: {e}")
        return

    print(f"\n  Form data:")
    for key in ("provider_url", "requested_item", "amount"):
        print(f"    {key:25s} = {safe(form_data.get(key, ''))}")

    # Step 2: Gather
    gatherer = WebGatherer()
    try:
        evidence = gatherer.gather(form_data)
    except Exception as e:
        print(f"\n  GATHER ERROR: {e}")
        return

    print(f"\n  Ref ID      : {evidence['ref_id']}")
    print(f"  URL         : {safe(evidence['url'])}")
    print(f"  Timestamp   : {evidence['timestamp']}")
    print(f"  Overall     : {evidence['overall_status']}")

    item = evidence["item"]
    print(f"\n  Item  ->  Status: {item['status']:12s}  Note: {item['note']}")

    amt = evidence["amount"]
    print(f"  Price ->  Status: {amt['status']:12s}  Note: {amt['note']}")

    for label, path in evidence["evidence_paths"].items():
        p = Path(path)
        ok = "OK" if p.exists() else "MISSING"
        sz = p.stat().st_size if p.exists() else 0
        print(f"  Evidence   : {label:15s}  {sz:>8,} bytes  [{ok}]")


def main():
    samples_dir = Path(__file__).resolve().parent.parent / "samples"

    tests = [
        ("Sample-01---Community-Class-GallopNYC.pdf",
         "Community Class - GallopNYC"),
        ("Sample-02---Community-Class-Gracie-Barra-Jiu-Jitsu.pdf",
         "Community Class - Gracie Barra Jiu-Jitsu"),
        ("Sample-03---Coaching-92NY-Parenting.pdf",
         "Coaching - 92NY Parenting"),
    ]

    for filename, label in tests:
        pdf_path = samples_dir / filename
        if not pdf_path.exists():
            print(f"  SKIPPED (not found): {pdf_path}")
            continue
        run_test(pdf_path, label)

    print(f"\n{'=' * 72}")
    print("  All gatherer tests completed.")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    main()