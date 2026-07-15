# AI Conversation Log — Pre-Approval Website-Verification Tool

This document summarizes the complete design and implementation conversation for the Pre-Approval Website-Verification Tool, built as a take-home interview project.

---

## 1. Problem Statement

**Context:** A non-profit human-services agency (the Agency) acts as a Fiscal Intermediary for OPWDD Self-Direction participants. Before participants can spend budget money on non-routine items (community classes, gym memberships, coaching courses, household items, etc.), a Pre-Approvals Reviewer must manually verify that the item/class is publicly available at a published price — by visiting the provider's website, finding the evidence, and saving date-stamped screenshots for Medicaid audits.

**Goal:** Build an automated agent that:
1. Reads a completed pre-approval application PDF (1 of 7 form types)
2. Extracts key fields: participant, provider name, provider URL, requested item/class, fee
3. Visits the provider URL and searches for the item and price
4. Captures date-stamped evidence (full-page screenshot + per-requirement screenshots)
5. Produces a professional, self-contained HTML report the reviewer can save/share

**Key constraint:** The tool **assists** — it never approves or denies. Final decision remains human.

---

## 2. Architectural Decisions

### 2.1 Four-Stage Pipeline

We chose a modular, decoupled architecture with four distinct stages communicating via typed Pydantic-like dictionaries:

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  PDF Parser │ →  │ Field Extractor │ → │ Evidence Gatherer │ → │ Report Generator │
│  (Stage 1)  │    │  (Stage 2)      │    │  (Stage 3)        │    │  (Stage 4)       │
└─────────────┘    └──────────────┘    └─────────────────┘    └─────────────────┘
```

| Stage | Module | Responsibility |
|-------|--------|----------------|
| 1 | `src/parser/` | Extract raw text + positional data from PDF; identify form type; return structured dict |
| 2 | (integrated in parser) | Normalize field names across form types; map "Class Name" / "Membership Name" / "Coaching Provider" → `requested_item` |
| 3 | `src/gatherer/` | Playwright-driven browser; navigate to URL; search page for item + price; inject compliance overlay; capture full-page screenshot |
| 4 | `src/reporter/` | Jinja2 template → self-contained HTML with base64-embedded screenshot; save to `reports/` |

**Why decoupled?** Each stage can be swapped, tested, or extended independently. New form types = new parser subclass + config YAML — no core logic changes.

---

### 2.2 Config-Driven Checklists (Section 5 Compliance)

The Project Brief §5 defines *which* checklist items are website-verifiable vs. internal. We encoded this as YAML per category (`config/community_class.yaml`, `config/coaching.yaml`, `config/memberships.yaml`):

```yaml
website_verifiable:
  - id: published_fees
    label: "Fees published on website"
    check_type: price_presence
  - id: fee_match
    label: "Fee matches application"
    check_type: price_compare
internal:
  - budget_approved
  - life_plan_alignment
  ...
```

**Benefit:** Non-engineers can add/modify categories by editing YAML — no code changes.

---

### 2.3 Evidence Capture & Date-Stamping (Section 5)

The brief requires: *"Both kinds [of evidence] must be date-stamped with a visible date/time of when the capture was taken… and must record the URL captured."*

**Our implementation:**

1. **Overlay injection** (`src/gatherer/gatherer.py:_inject_overlay`):
   - Before screenshot, `page.evaluate()` injects a fixed-position `<div>` at top of viewport
   - Contains: `Verification Timestamp: <ISO-8601>`, `Source URL: <current URL>`, `Ref: <VERIFY-YYYYMMDD-XXXXXX>`
   - Styled as a dark header bar; page content pushed down so nothing is obscured

2. **Full-page screenshot** (`page.screenshot(full_page=True)`):
   - Captures entire scrollable page with overlay baked into pixels
   - Saved as PNG to `evidence/VERIFY-<ref>_fullpage.png`

3. **Base64 embedding in HTML report** (`src/reporter/generator.py`):
   - Screenshot read as bytes → base64 → `data:image/png;base64,…` data URI
   - Report is a single `.html` file — open in any browser, no external assets needed

4. **Audit trail metadata** in report:
   - Ref ID, timestamp, source URL, overall status, per-field status + snippet

---

### 2.4 Tech Stack Rationale

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.13 | Already in environment; rich ecosystem |
| PDF | PyMuPDF (`fitz`) | Fast, positional text extraction (`get_text("dict")`), handles scanned/exported PDFs |
| Web | Playwright (sync API) | Renders JS-heavy sites, `networkidle` wait, reliable screenshots, headless Chromium |
| Template | Jinja2 | Standard, auto-escaping, template inheritance |
| CLI | `argparse` (stdlib) | Zero deps, simple |
| Config | YAML | Human-readable, version-controllable |

---

## 3. Handling Edge Cases (from Sample PDFs)

| Edge Case | Sample | Mitigation |
|-----------|--------|------------|
| **Top-level domain URL** | Gracie Barra → `graciebarra.com` (homepage) | Tool navigates to URL; honest "Not Found" if class/price not on landing page |
| **3-column label row** | Community Class "Subject Area / Fee / Duration" row | Column-index matching: label at index N → value at index N in next row |
| **Multi-page PDFs** | Community Class = 2 pages | Page-height offset (`page_idx * page_height`) prevents cross-page row interleaving |
| **Unicode in PDFs** | Smart quotes (’), checkboxes (☑) | `_norm()` replaces common Unicode; cp1252-safe printing in CLI |
| **Price format variation** | "$80 per 30-minute session" vs "$30 per session" | Regex fallback extracts first `$…` pattern; exact string match tried first |
| **Dynamic/JS sites** | All samples | Playwright waits `networkidle`; renders fully |
| **Missing URL on form** | Not in samples, but brief requires | Parser returns empty → gatherer returns structured error result |
| **Price not published** | Real-world common | Gatherer reports "Not Found" with snippet — never fabricates |

---

## 4. Testing Results (3 Sample PDFs)

| Sample | Form Type | Provider URL | Item Verified | Price Verified | Screenshot | Report |
|--------|-----------|--------------|---------------|----------------|------------|--------|
| **Sample-01** GallopNYC | Community Class | `gallopnyc.org/recreational-riding` | ✅ **Verified** (keywords: Recreational, Group, Riding) | ❌ Not Found (price not on page) | 999 KB | `report_VERIFY-20260715-EA9D96.html` |
| **Sample-02** Gracie Barra | Community Class | `graciebarra.com` (homepage) | ❌ Not Found (class not on homepage) | ❌ Not Found | 3.3 MB | `report_VERIFY-20260715-BAAF61.html` |
| **Sample-03** 92NY Parenting | Coaching | `92ny.org/parenting-and-family` | ✅ **Verified** (keywords: 92NY, Family, Center) | ❌ Not Found ($50 not on page) | 764 KB | `report_VERIFY-20260715-898F17.html` |

**All reports:**
- Self-contained HTML (~1.3 MB each with embedded base64 PNG)
- Open directly in browser — compliance overlay visible at top
- Status badges: green "Verified" / amber "Not Found"
- Per-field snippet showing what was matched

---

## 5. Repository Structure (Final)

```
trial/
├── PLAN.md                    # Full architecture & risk assessment
├── AI-CONVERSATION.md         # This file
├── README.md                  # Quick-start & usage
├── requirements.txt           # Python deps
├── config/
│   ├── community_class.yaml   # Website-verifiable + internal checklists
│   ├── coaching.yaml
│   └── memberships.yaml
├── src/
│   ├── main.py                # CLI: Parse → Gather → Report
│   ├── parser/
│   │   ├── __init__.py
│   │   └── parser.py          # BaseParser + 3 form parsers + positional extraction
│   ├── gatherer/
│   │   ├── __init__.py
│   │   └── gatherer.py        # WebGatherer: Playwright + overlay + verification
│   ├── reporter/
│   │   ├── __init__.py
│   │   ├── generator.py       # ReportGenerator (Jinja2 + base64 embed)
│   │   └── templates/
│   │       └── report_template.html
│   └── utils/
│       └── __init__.py
├── samples/                   # 5 PDFs (3 applications + 2 briefs)
├── evidence/                  # Date-stamped PNG screenshots
│   ├── VERIFY-20260715-*.png
├── reports/                   # Self-contained HTML reports
│   ├── report_VERIFY-20260715-*.html
└── tests/
    ├── test_parser.py         # Unit test: parser on all 3 samples
    └── test_gatherer.py       # Integration test: parser + gatherer on all 3
```

---

## 6. Known Limitations & Production Gaps

| Area | Current | Production Would Need |
|------|---------|----------------------|
| PHI handling | Sample data only | On-prem / VPC; local LLM (Ollama); audit logging |
| Site navigation | Single-page only | Crawl/sitemap follow; button clicks for "View Pricing" |
| Rate limiting | None | Politeness delay, `robots.txt` respect, retry/backoff |
| Checklist coverage | 3 of 7 forms | HRI, OTPS, Transition, Appeals parsers + YAML |
| Interaction | CLI only | Streamlit/Gradio UI for reviewer "chat" loop (§7) |
| CI/CD | None | GitHub Actions: lint, type-check, sample regression test |

---

## 7. How to Run

```bash
# 1. Prerequisites
Python 3.13+
pip install -r requirements.txt
playwright install chromium

# 2. Run on a sample
python -m src.main samples/Sample-01---Community-Class-GallopNYC.pdf

# 3. Output
# reports/report_VERIFY-<ref>.html  ← open in browser
# evidence/VERIFY-<ref>_fullpage.png
```

---

*Generated as part of the take-home evaluation for the Pre-Approval Website-Verification Tool.*