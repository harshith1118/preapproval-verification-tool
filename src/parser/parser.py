"""
PDF Parser Module

Extracts structured data from pre-approval application PDFs using
PyMuPDF positional data.  Handles three form categories with a
config-driven, column-index matching approach that is robust to
scanned / exported PDFs with varying layouts.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import fitz


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Replace common Unicode punctuation that PDF extraction leaves behind."""
    for old, new in [
        ("\u2019", "'"), ("\u2018", "'"),
        ("\u201c", '"'), ("\u201d", '"'),
        ("\u2013", "-"), ("\u2014", "-"),
        ("\u00a0", " "),
        ("\u2011", "-"), ("\ufb01", "fi"), ("\ufb02", "fl"),
    ]:
        text = text.replace(old, new)
    return text.strip()


# ---------------------------------------------------------------------------
# Positional helpers
# ---------------------------------------------------------------------------

_ROW_TOLERANCE = 5        # vertical tolerance (points) for row grouping
_COL_GAP_THRESHOLD = 40   # minimum horizontal gap to start a new column


def _get_items(doc: fitz.Document) -> list[dict[str, Any]]:
    """Return all text fragments from *doc* sorted by (page, y, x).

    A page-height offset is added to *y* so that items from different
    pages never interleave — this preserves the "label row immediately
    followed by its value row" invariant across multi-page PDFs.
    """
    items: list[dict[str, Any]] = []
    for page_idx, page in enumerate(doc):
        page_offset = page_idx * page.rect.height + 1
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:          # skip images
                continue
            for line in block["lines"]:
                text = _norm("".join(s["text"] for s in line["spans"]))
                if not text:
                    continue
                x0, y0, _x1, _y1 = line["bbox"]
                items.append({
                    "text": text,
                    "x0": x0,
                    "y0": y0,
                    "y_sorted": page_offset + y0,
                })
    items.sort(key=lambda i: (i["y_sorted"], i["x0"]))
    return items


def _group_rows(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group *items* into rows by their sorted y-position."""
    if not items:
        return []
    rows: list[list[dict[str, Any]]] = []
    cur_y = items[0]["y_sorted"]
    cur_row: list[dict[str, Any]] = []
    for item in items:
        if abs(item["y_sorted"] - cur_y) <= _ROW_TOLERANCE:
            cur_row.append(item)
        else:
            if cur_row:
                cur_row.sort(key=lambda i: i["x0"])
                rows.append(cur_row)
            cur_row = [item]
            cur_y = item["y_sorted"]
    if cur_row:
        cur_row.sort(key=lambda i: i["x0"])
        rows.append(cur_row)
    return rows


def _extract_value(rows: list[list[dict[str, Any]]], label_text: str) -> str:
    """
    Find the label *label_text* in a row and return the value from the
    same column index in the immediately following row.
    """
    for row_idx, row in enumerate(rows):
        if row_idx + 1 >= len(rows):
            break
        for col_idx, item in enumerate(row):
            if label_text in item["text"]:
                next_row = rows[row_idx + 1]
                if col_idx < len(next_row):
                    return next_row[col_idx]["text"]
                if next_row:
                    return next_row[0]["text"]
    return ""


# ---------------------------------------------------------------------------
# Fallback: regex extraction from raw text
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s]+")
_PRICE_RE = re.compile(r"\$?\d+(?:[.,]\d+)?(?:\s*(?:per|/)\s*\w+)?")
_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")


def _fallback_extract(full_text: str, field_name: str, label: str) -> str:
    """Regex-based fallback when positional extraction misses a field."""
    # URL fallback: look for a URL near the label
    if field_name == "provider_url":
        match = _URL_RE.search(full_text)
        if match:
            url = match.group()
            if not url.endswith(".pdf") and "example" not in url:
                return url
    # Amount fallback: find first price-like pattern in the text
    if field_name == "amount" or field_name.endswith("fee"):
        matches = _PRICE_RE.findall(full_text)
        if matches:
            return matches[0]
    return ""


# ---------------------------------------------------------------------------
# Base parser
# ---------------------------------------------------------------------------

class BaseParser(ABC):
    """Abstract base for all form-type parsers."""

    @property
    @abstractmethod
    def form_type(self) -> str:
        """Machine-readable category identifier."""

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        """Return True if this parser applies to *text*."""

    @abstractmethod
    def field_defs(self) -> dict[str, str]:
        """Map {output_field_name: label_text_to_find}."""

    def parse(self, doc: fitz.Document) -> dict[str, Any]:
        """Run positional extraction for all defined fields."""
        items = _get_items(doc)
        rows = _group_rows(items)
        result: dict[str, Any] = {"form_type": self.form_type}

        # Full text for fallback
        full_text = _norm("".join(i["text"] for i in items))

        for field_name, label_text in self.field_defs().items():
            value = _extract_value(rows, label_text)
            if not value:
                value = _fallback_extract(full_text, field_name, label_text)
            result[field_name] = value

        return result


# ---------------------------------------------------------------------------
# Community Classes
# ---------------------------------------------------------------------------

class CommunityClassParser(BaseParser):
    """Parser for the 'Community Class Pre-approval Checklist' form."""

    form_type = "community_class"

    def can_handle(self, text: str) -> bool:
        return "Community Class Pre-approval Checklist" in text

    def field_defs(self) -> dict[str, str]:
        return {
            "participant_name": "Participant's Name",
            "participant_age": "Participant's Age",
            "fi_coordinator": "FI Coordinator Name",
            "broker_name": "Broker Name",
            "requested_item": "Class Name",
            "provider_name": "Name of Provider/Vendor",
            "provider_url": "Link to Webpage",
            "subject_area": "Subject Area/Skill",
            "amount": "Fee per Session",
            "duration": "Duration per Session",
        }


# ---------------------------------------------------------------------------
# Coaching (for Parents / Spouse)
# ---------------------------------------------------------------------------

class CoachingParser(BaseParser):
    """Parser for the 'Coaching for Parents/Spouse Pre-approval Form'."""

    form_type = "coaching"

    def can_handle(self, text: str) -> bool:
        return "Coaching for Parents/Spouse Pre-approval Form" in text

    def field_defs(self) -> dict[str, str]:
        return {
            "participant_name": "Participant's Name",
            "participant_age": "Participant's Age",
            "fi_coordinator": "FI Coordinator Name",
            "broker_name": "Broker Name",
            "provider_name": "Name of Coaching Provider",
            "requested_item": "Name of Coaching Provider",
            "provider_url": "Link to Webpage",
            "amount": "Fee per Class",
            "fee_per_course": "Fee per Course",
        }


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------

class MembershipParser(BaseParser):
    """Parser for the 'Memberships preapproval form'."""

    form_type = "membership"

    def can_handle(self, text: str) -> bool:
        return any(p in text for p in ("Memberships preapproval", "Membership Pre-approval", "Health-Club"))

    def field_defs(self) -> dict[str, str]:
        return {
            "participant_name": "Participant's Name",
            "participant_age": "Participant's Age",
            "fi_coordinator": "FI Coordinator Name",
            "broker_name": "Broker Name",
            "requested_item": "Membership Name",
            "provider_name": "Name of Organization",
            "provider_url": "Link to Webpage",
            "amount": "Membership Fee",
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class PDFParser:
    """
    Top-level parser that detects the form category and dispatches to the
    appropriate :class:`BaseParser` subclass.
    """

    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)
        self._parsers: list[BaseParser] = [
            CommunityClassParser(),
            CoachingParser(),
            MembershipParser(),
        ]

    def parse(self) -> dict[str, Any]:
        """
        Open the PDF, classify it, extract fields, and return a clean
        dictionary with all recognised fields.
        """
        if not self.filepath.exists():
            raise FileNotFoundError(f"PDF not found: {self.filepath}")

        try:
            doc = fitz.open(str(self.filepath))
        except Exception as exc:
            raise ValueError(f"Failed to open PDF: {exc}") from exc

        try:
            full_text = ""
            for page in doc:
                full_text += page.get_text()
            full_text = _norm(full_text)

            if not full_text.strip():
                raise ValueError("PDF contains no extractable text")

            for parser in self._parsers:
                if parser.can_handle(full_text):
                    result = parser.parse(doc)
                    result["_source_file"] = str(self.filepath)
                    result["_status"] = "ok"
                    return result

            raise ValueError(
                f"Unrecognised form type in '{self.filepath.name}'. "
                f"Expected one of: community_class, coaching, membership."
            )
        finally:
            doc.close()
