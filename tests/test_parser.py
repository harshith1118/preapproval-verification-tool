"""
Test the PDF parser against the three provided sample application forms.

Usage:
    python tests/test_parser.py
"""

import json
import sys
from pathlib import Path

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser.parser import PDFParser


def safe(text: str) -> str:
    """Replace characters that choke cp1252 so we can print safely."""
    return text.encode("ascii", "replace").decode("ascii")


def run_test(pdf_path: Path, label: str) -> None:
    """Parse a single sample and print the result."""
    print(f"\n{'=' * 72}")
    print(f"  {label}")
    print(f"  File: {pdf_path.name}")
    print(f"{'=' * 72}")

    try:
        result = PDFParser(str(pdf_path)).parse()
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return

    print(f"  Status : {result.pop('_status', '?')}")
    print(f"  Source : {result.pop('_source_file', '?')}")
    print(f"  Form   : {result.pop('form_type', '?')}")
    print(f"\n  Extracted fields:")
    for key, value in result.items():
        display = safe(value) if value else "(empty)"
        print(f"    {key:25s} = {display}")


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
    print("  All tests completed.")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    main()