"""
Report Generator Module

Renders the final review-ready HTML report using the Jinja2 template.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "reports"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _encode_image(path: Path) -> str:
    """Read image file and return base64 data URI for embedding in HTML."""
    if not path.exists():
        return ""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------

class ReportGenerator:
    """
    Assembles parsed application data + gathered evidence into a single
    self-contained HTML report with embedded screenshot.
    """

    def __init__(self, template_name: str = "report_template.html"):
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template = self._env.get_template(template_name)
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        application: dict[str, Any],
        verification: dict[str, Any],
        evidence: dict[str, Any],
        output_name: str | None = None,
    ) -> Path:
        """
        Render the HTML report and write to disk.

        Parameters
        ----------
        application : dict
            Output from PDFParser.parse()
        verification : dict
            Output from WebGatherer.gather() (the 'item' and 'amount' blocks)
        evidence : dict
            Evidence dict from WebGatherer.gather() (evidence_paths, ref_id, etc.)
        output_name : str | None
            Optional custom filename stem (without extension).

        Returns
        -------
        Path
            Path to the generated HTML file.
        """
        # Build template context
        ref_id = evidence.get("ref_id", f"VERIFY-{datetime.now().strftime('%Y%m%d')}")
        evidence_path = evidence.get("evidence_paths", {}).get("page_capture")

        context = {
            "report": {
                "ref_id": ref_id,
                "timestamp": _now_iso(),
                "overall_status": evidence.get("overall_status", "Not Found"),
            },
            "application": {
                "participant_name": application.get("participant_name", ""),
                "participant_age": application.get("participant_age", ""),
                "fi_coordinator": application.get("fi_coordinator", ""),
                "broker_name": application.get("broker_name", ""),
                "form_type": application.get("form_type", ""),
                "amount_requested": application.get("amount", ""),
                "requested_item": application.get("requested_item", ""),
                "provider_name": application.get("provider_name", ""),
                "provider_url": application.get("provider_url", ""),
            },
            "verification": {
                "item": {
                    "status": verification.get("item", {}).get("status", "Not Found"),
                    "found_snippet": verification.get("item", {}).get("found_content", ""),
                    "note": verification.get("item", {}).get("note", ""),
                },
                "amount": {
                    "status": verification.get("amount", {}).get("status", "Not Found"),
                    "found_snippet": verification.get("amount", {}).get("found_content", ""),
                    "note": verification.get("amount", {}).get("note", ""),
                },
            },
            "evidence": {
                "ref_id": ref_id,
                "timestamp": evidence.get("timestamp", _now_iso()),
                "url": evidence.get("url", application.get("provider_url", "")),
                "data_uri": _encode_image(Path(evidence_path)) if evidence_path else "",
            },
        }

        html = self._template.render(**context)

        # Determine output filename
        stem = output_name or f"report_{ref_id}"
        out_path = _OUTPUT_DIR / f"{stem}.html"
        out_path.write_text(html, encoding="utf-8")
        return out_path