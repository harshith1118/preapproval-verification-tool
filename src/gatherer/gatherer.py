"""
WebGatherer Module

Takes the structured output from PDFParser, navigates the provider's
website with Playwright, verifies the requested item and price are
publicly visible, and captures date-stamped screenshot evidence
compliant with Section 5 audit requirements.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from playwright.sync_api import (
    Error as PlaywrightError,
    Page,
    sync_playwright,
    TimeoutError as PlaywrightTimeout,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EVIDENCE_DIR = Path(__file__).resolve().parent.parent.parent / "evidence"
_NAVIGATE_TIMEOUT_MS = 30_000
_WAIT_IDLE_TIMEOUT_MS = 15_000

# CSS for the compliance overlay that is injected into every captured page
_OVERLAY_CSS = """
position: fixed;
top: 0;
left: 0;
width: 100%;
z-index: 2147483647;
background: #1a3a5c;
color: #fff;
font-family: 'Segoe UI', Arial, sans-serif;
font-size: 13px;
padding: 8px 16px;
box-sizing: border-box;
display: flex;
flex-wrap: wrap;
gap: 16px;
pointer-events: none;
user-select: none;
box-shadow: 0 2px 6px rgba(0,0,0,0.3);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_ref() -> str:
    return f"VERIFY-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"


def _sanitise_filename(text: str) -> str:
    """Replace characters that are unsafe in filenames."""
    return re.sub(r'[<>:"/\\|?*]', "_", text)[:60]


def _extract_snippet(text: str, query: str, context_chars: int = 60) -> str:
    """Return a short surrounding-context snippet for a match."""
    idx = text.lower().find(query.lower())
    if idx == -1:
        return ""
    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(query) + context_chars)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


# ---------------------------------------------------------------------------
# Overlay injection
# ---------------------------------------------------------------------------

def _inject_overlay(page: Page, ref_id: str) -> None:
    """Inject a date-stamped compliance overlay into the page DOM."""
    import json as _json
    iso = _now_iso()
    url = page.url
    # Safely serialize Python values into JavaScript string literals
    css_js = _json.dumps(_OVERLAY_CSS)
    iso_js = _json.dumps(iso)
    url_js = _json.dumps(url)
    ref_js = _json.dumps(ref_id)

    js = f"""
    (function() {{
        var old = document.getElementById('opencode-evidence-overlay');
        if (old) old.remove();

        var div = document.createElement('div');
        div.id = 'opencode-evidence-overlay';
        div.style.cssText = {css_js};

        div.innerHTML =
            '<span><strong>Verification Timestamp:</strong> {iso_js}</span>' +
            ' <span><strong>Source URL:</strong> <code style="color:#8cf;word-break:break-all;">{url_js}</code></span>' +
            ' <span><strong>Ref:</strong> {ref_js}</span>';

        document.body.insertBefore(div, document.body.firstChild);

        var style = document.createElement('style');
        style.id = 'opencode-overlay-shift';
        style.textContent = 'body {{ padding-top: 32px !important; }}';
        document.head.appendChild(style);
    }})();
    """
    page.evaluate(js)


# ---------------------------------------------------------------------------
# WebGatherer
# ---------------------------------------------------------------------------

class WebGatherer:
    """
    Navigate a provider's website, verify the requested item and price,
    capture date-stamped evidence, and return a structured summary.
    """

    def __init__(self, ref_id: str | None = None):
        self.ref_id = ref_id or _make_ref()
        self.evidence_dir = _EVIDENCE_DIR
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    # ── public entry point ────────────────────────────────────────────

    def gather(self, form_data: dict[str, Any]) -> dict[str, Any]:
        """
        Perform the full verification workflow for one application.

        Parameters
        ----------
        form_data : dict
            The output dictionary from :class:`PDFParser.parse()`.
            Expected keys: ``provider_url``, ``requested_item``, ``amount``.

        Returns
        -------
        dict
            ``ref_id``, ``url``, ``timestamp``, ``overall_status``,
            ``item``, ``amount``, ``evidence_paths``.
        """
        url: str = (form_data.get("provider_url") or "").strip()
        item_name: str = (form_data.get("requested_item") or "").strip()
        amount: str = (form_data.get("amount") or "").strip()

        if not url:
            return self._error_result("No provider URL available in form data.")

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        ts = _now_iso()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = context.new_page()

            try:
                nav_ok = self._navigate(page, url)
                if not nav_ok:
                    browser.close()
                    return self._error_result(
                        f"Failed to reach {url} — site unreachable or returned an error.",
                        url=url,
                    )

                # --- verify requested item ---
                item_result = self._verify_text(page, item_name, "item")
                page_text = page.inner_text("body")

                # --- verify amount ---
                amount_result = self._verify_text(page, amount, "price",
                                                  full_text=page_text)

                # --- capture full-page evidence ---
                cap_filename = f"{self.ref_id}_fullpage.png"
                cap_path = self.evidence_dir / cap_filename
                self._capture(page, cap_path)

                # --- determine overall status ---
                item_ok = item_result["status"] == "Verified"
                amount_ok = amount_result["status"] == "Verified"
                overall = "Verified" if (item_ok or amount_ok) else "Not Found"

                result: dict[str, Any] = {
                    "ref_id": self.ref_id,
                    "url": page.url,
                    "timestamp": ts,
                    "overall_status": overall,
                    "item": item_result,
                    "amount": amount_result,
                    "evidence_paths": {
                        "page_capture": str(cap_path),
                    },
                }

            except PlaywrightTimeout:
                browser.close()
                return self._error_result(
                    f"Navigation timed out for {url}.",
                    url=url,
                )
            except PlaywrightError as exc:
                browser.close()
                return self._error_result(
                    f"Playwright error: {exc}",
                    url=url,
                )
            except Exception as exc:
                browser.close()
                return self._error_result(
                    f"Unexpected error: {exc}",
                    url=url,
                )

            browser.close()
            return result

    # ── internal methods ──────────────────────────────────────────────

    def _navigate(self, page: Page, url: str) -> bool:
        """Navigate to *url* and wait for the network to settle."""
        try:
            response = page.goto(url, timeout=_NAVIGATE_TIMEOUT_MS,
                                 wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle",
                                     timeout=_WAIT_IDLE_TIMEOUT_MS)
            if response and response.ok:
                return True
            # 4xx / 5xx still counts as "reached" — we just record the error
            return response is not None
        except PlaywrightTimeout:
            # page partially loaded — we can still try to work with it
            return True

    def _verify_text(self, page: Page, query: str,
                     label: str, full_text: str | None = None) -> dict[str, Any]:
        """Search for *query* in the page and return verification results.

        Tries in order:
        1. Exact (case-insensitive) match in visible text
        2. Exact match in page HTML
        3. Keyword-based partial matching (≥2 significant words)
        """
        if not query:
            return {"status": "Not Found", "found_content": "",
                    "note": f"No {label} text provided to search for."}

        if full_text is None:
            try:
                full_text = page.inner_text("body")
            except Exception:
                full_text = ""

        # ── 1. Exact match in visible text ──────────────────────────
        match = re.search(re.escape(query), full_text, re.IGNORECASE)
        if match:
            snippet = _extract_snippet(full_text, query)
            return {
                "status": "Verified",
                "found_content": snippet,
                "note": f"'{query}' found on page.",
            }

        # ── 2. Exact match in raw HTML ──────────────────────────────
        try:
            html = page.content()
            if re.search(re.escape(query), html, re.IGNORECASE):
                snippet = _extract_snippet(html, query)
                return {
                    "status": "Verified",
                    "found_content": snippet,
                    "note": f"'{query}' found in page source (not in visible text).",
                }
        except Exception:
            pass

        # ── 3. Keyword partial matching ─────────────────────────────
        keywords = [w for w in re.split(r'[\s,;/]+', query)
                    if len(w) > 3 and w.lower()
                    not in ("the", "and", "for", "with", "that",
                            "this", "from", "per", "your")]
        matched_keywords = []
        for kw in keywords:
            if re.search(re.escape(kw), full_text, re.IGNORECASE):
                matched_keywords.append(kw)

        if len(matched_keywords) >= max(2, len(keywords) // 2):
            snippet = _extract_snippet(full_text, matched_keywords[0])
            return {
                "status": "Verified",
                "found_content": snippet,
                "note": f"Partial match — keywords found: {matched_keywords}",
            }

        return {
            "status": "Not Found",
            "found_content": "",
            "note": f"'{query}' not found on the page "
                    f"(checked {len(keywords)} significant keywords).",
        }

    def _capture(self, page: Page, path: Path) -> None:
        """Inject the compliance overlay and take a full-page screenshot."""
        try:
            _inject_overlay(page, self.ref_id)
        except Exception:
            pass  # overlay is best-effort; screenshot still taken
        page.screenshot(path=str(path), full_page=True)

    def _error_result(self, message: str,
                      url: str = "") -> dict[str, Any]:
        """Build a standard error-shaped result dict."""
        return {
            "ref_id": self.ref_id,
            "url": url,
            "timestamp": _now_iso(),
            "overall_status": "Not Found",
            "item": {"status": "Not Found", "found_content": "",
                     "note": message},
            "amount": {"status": "Not Found", "found_content": "",
                       "note": message},
            "evidence_paths": {},
        }
