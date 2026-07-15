# Pre-Approval Website-Verification Tool

Automated evidence-gathering agent for OPWDD Self-Direction pre-approval reviews.

## Overview

Staff at a NY non-profit agency review purchase-approval applications for government-funded disability services. Before approving a community class, gym membership, coaching course, or household item, a reviewer must visit the provider's public website and confirm:

- The item/class exists and is open to the public
- Fees are published and match the application
- Screenshots are captured with date/time stamps for Medicaid audit trail

**This tool automates that workflow.** It reads the PDF application, navigates to the provider URL, searches for the item and price, captures a compliance-stamped full-page screenshot, and generates a self-contained HTML report.

> ⚠️ **The tool assists the reviewer — it never approves or denies.** Final determination is always human.

---

## Quick Start

### Prerequisites
- Python 3.13+
- Playwright Chromium

```bash
# 1. Clone / enter repo
cd trial

# 2. Create venv & install deps
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Install Playwright browser
playwright install chromium
```

### Run on a Sample Application

```bash
# GallopNYC community class (recommended first — deep link with content)
python -m src.main samples/Sample-01---Community-Class-GallopNYC.pdf

# Gracie Barra (homepage only — class not on landing page)
python -m src.main samples/Sample-02---Community-Class-Gracie-Barra-Jiu-Jitsu.pdf

# 92NY Parenting coaching (deep link with content)
python -m src.main samples/Sample-03---Coaching-92NY-Parenting.pdf
```

### Output
```
Processing: Sample-01---Community-Class-GallopNYC.pdf
Step 1/3: Parsing PDF...
  ✓ Parsed as: community_class
Step 2/3: Verifying on provider website...
  ✓ Item: Verified | Amount: Not Found | Overall: Verified
Step 3/3: Generating HTML report...
  ✓ Report saved: reports/report_VERIFY-20260715-EA9D96.html
  ✓ Evidence: evidence/VERIFY-20260715-EA9D96_fullpage.png
```

Open the HTML report in any browser — it contains the embedded screenshot with the audit overlay.

---

## CLI Reference

```bash
python -m src.main <pdf_path> [options]

Options:
  -o, --output NAME    Custom output filename stem (default: report_<ref_id>)
  --json               Print structured JSON to stdout instead of generating HTML
  --no-report          Skip HTML generation (parse + gather only)
  --timeout SECS       Navigation timeout (default: 30)
```

---

## Project Structure

```
trial/
├── src/
│   ├── main.py                    # CLI entry point
│   ├── parser/                    # Stage 1: PDF → structured dict
│   │   └── parser.py              # BaseParser + 3 form-specific parsers
│   ├── gatherer/                  # Stage 2: Playwright verification
│   │   └── gatherer.py            # WebGatherer + overlay injection
│   └── reporter/                  # Stage 3: HTML report
│       ├── generator.py           # ReportGenerator (Jinja2 + base64)
│       └── templates/
│           └── report_template.html
├── config/                        # Checklist definitions (YAML)
│   ├── community_class.yaml
│   ├── coaching.yaml
│   └── memberships.yaml
├── samples/                       # 3 test applications + 2 briefs
├── evidence/                      # Date-stamped PNG screenshots
├── reports/                       # Self-contained HTML reports
├── PLAN.md                        # Full architecture doc
├── AI-CONVERSATION.md             # This conversation log
├── requirements.txt
└── README.md
```

---

## How It Works

### 1. PDF Parsing (`src/parser/parser.py`)
- Uses **PyMuPDF** `get_text("dict")` to extract text spans with (x, y) coordinates
- Groups spans into rows by y-tolerance; sorts each row by x → left/right columns
- **Page-height offset** (`page_idx * page_height`) prevents cross-page row interleaving in multi-page PDFs
- Detects form type by header text ("Community Class Pre-approval Checklist", "Coaching for Parents/Spouse…")
- Maps form-specific labels to canonical fields:
  - `Class Name` / `Membership Name` / `Coaching Provider` → `requested_item`
  - `Fee per Session` / `Fee per Class` / `Membership Fee` → `amount`
  - `Link to Webpage…` / `Link to Webpage` → `provider_url`

### 2. Web Verification (`src/gatherer/gatherer.py`)
- **Playwright** launches headless Chromium
- Navigates to `provider_url`; waits `networkidle` (JS rendered)
- **Three-tier search** for item and price:
  1. Exact case-insensitive match in visible text
  2. Exact match in raw HTML (catches hidden/attribute text)
  3. Keyword partial match (≥2 significant words from query)
- **Compliance overlay** injected via `page.evaluate()` before screenshot:
  - Fixed top bar: `Verification Timestamp: <ISO-8601>` | `Source URL: <url>` | `Ref: VERIFY-YYYYMMDD-XXXXXX`
  - Page content pushed down so nothing is obscured
- **Full-page screenshot** → `evidence/VERIFY-<ref>_fullpage.png`

### 3. Report Generation (`src/reporter/generator.py`)
- **Jinja2** template → `report_VERIFY-<ref>.html`
- Screenshot embedded as **base64 data URI** → single-file, no external assets
- Report sections:
  - Header: ref ID, timestamp, overall status badge
  - Application details: participant, provider, item, amount, URL
  - Verification cards: item check + amount check (status, snippet, note)
  - Evidence: embedded screenshot + metadata (ref, timestamp, URL)
- Footer disclaimer: tool assists, does not decide

---

## Config-Driven Checklists

The Project Brief §5 defines which checklist items are website-verifiable vs. internal. We encode this as YAML per category:

```yaml
# config/community_class.yaml
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
  # …
```

Add a new form type → drop a new YAML file + a `BaseParser` subclass — **no core logic changes**.

---

## Sample Results

| Sample | Form | Provider | Item Status | Price Status | Evidence |
|--------|------|----------|-------------|--------------|----------|
| Sample-01 | Community Class | gallopnyc.org/recreational-riding | ✅ Verified (keywords: Recreational, Group, Riding) | ❌ Not Found | 999 KB |
| Sample-02 | Community Class | graciebarra.com (homepage) | ❌ Not Found | ❌ Not Found | 3.3 MB |
| Sample-03 | Coaching | 92ny.org/parenting-and-family | ✅ Verified (keywords: 92NY, Family, Center) | ❌ Not Found | 764 KB |

> **Honest "Not Found" is correct** — the tool never fabricates. Gracie Barra's homepage doesn't list the specific class or price; the reviewer would need to navigate further manually.

---

## Requirements

```
pymupdf>=1.27.0
pdfplumber>=0.11.0
playwright>=1.50.0
jinja2>=3.1.0
pyyaml>=6.0
```

---

## Production Readiness Notes

| Area | Current | Needed for Production |
|------|---------|----------------------|
| PHI / privacy | Sample data only | On-prem deployment; local LLM (Ollama); no external API calls |
| Site navigation | Single page only | Crawl/sitemap; click "Pricing"/"Schedule" links |
| Rate limiting | None | Politeness delay; `robots.txt` respect; exponential backoff |
| Checklist coverage | 3 of 7 forms | HRI, OTPS, Transition, Appeals parsers + YAML |
| Reviewer UI | CLI only | Streamlit/Gradio chat loop (§7 brief) |
| CI/CD | None | GitHub Actions: lint, type-check, sample regression tests |

---

## License

Internal evaluation project — not for public distribution.