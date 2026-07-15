# Pre-Approval Website-Verification Tool — Project Plan

## 1. Goal

Build an automated agent that reads a PDF pre-approval application, extracts the provider's website and requested item details, researches the website to verify legitimacy and price, captures date-stamped evidence, and generates a final review-ready report for a human reviewer.

The tool assists — it never approves or denies. A human always makes the final decision.

---

## 2. Proposed Tech Stack

| Layer              | Choice                     | Rationale                                                                 |
|--------------------|----------------------------|---------------------------------------------------------------------------|
| Language           | Python 3.13                | Existing on system; rich PDF, web, and ML ecosystem.                      |
| PDF Extraction     | **PyMuPDF (fitz)** + **pdfplumber** | PyMuPDF for text extraction; pdfplumber for table/checkbox detection.    |
| LLM / NLP          | **LangChain** + **GPT-4o-mini**     | Structured field extraction and ambiguity resolution from messy forms.    |
| Web Scraping       | **Playwright** (async)     | Renders JavaScript-heavy sites; supports screenshot & PDF capture natively. |
| Evidence Capture   | Playwright `page.screenshot()` + `page.pdf()` | Date-stamp overlay via DOM injection before capture.                      |
| Config             | **YAML**                   | Human-readable checklist definitions; new categories = new YAML file.     |
| Reporting          | **Jinja2 → HTML**          | Clean, shareable report with embedded screenshots.                        |
| CLI                | **Click** + **Rich**       | Minimal invocation path; Rich for pretty console output.                  |

---

## 3. Modular Architecture

The system is split into four decoupled stages, communicating via well-defined data classes (Pydantic models):

```
                         ┌──────────────────┐
                         │   PDF Parser      │  Stage 1
                         │  (strategy per    │
                         │   form type)      │
                         └───────┬──────────┘
                                 │ raw_text, checkbox_map
                                 ▼
                         ┌──────────────────┐
                         │  Field Extractor  │  Stage 2
                         │  (LLM + rules)    │
                         │                   │
                         │  → Normalize      │
                         │  → Classify       │
                         │  → Validate URL   │
                         └───────┬──────────┘
                                 │ RequestDetails (Pydantic)
                                 ▼
                         ┌──────────────────┐
                         │ Evidence Gatherer │  Stage 3
                         │ (Playwright agent)│
                         │                   │
                         │  → Navigate site  │
                         │  → Find item      │
                         │  → Extract price  │
                         │  → Date-stamp     │
                         │  → Screenshots    │
                         └───────┬──────────┘
                                 │ ChecklistResults + EvidenceFiles
                                 ▼
                         ┌──────────────────┐
                         │ Report Generator  │  Stage 4
                         │ (Jinja2 → HTML)   │
                         │                   │
                         │  → Summary header │
                         │  → Per-item table │
                         │  → Embed evidence │
                         │  → Internal flag  │
                         └──────────────────┘
```

### Stage 1 — PDF Parser

- Accepts a PDF file path.
- Uses PyMuPDF to extract raw text per page.
- Uses pdfplumber to detect checkbox fill states (checked/unchecked).
- Returns a `RawForm` object: `{text: str, checkboxes: dict[str, bool], path: str}`.
- Supports a strategy pattern: one parser per form category, registered by form title heuristics.

### Stage 2 — Field Extractor

- A LangChain chain that takes `RawForm` → `RequestDetails`.
- Structured output with Pydantic `RequestDetails`:
  - `participant_name`, `age`, `fi_coordinator`, `broker`
  - `category: str` (one of the 7)
  - `provider_name`, `website_url` (validated + normalized)
  - `item_name`, `fee_requested`, `fee_unit` (per session / per month / etc.)
  - `checkbox_answers: dict[str, bool]`
- If the URL is missing or invalid, the chain halts and asks the user.
- If the category is ambiguous, the chain asks for clarification.

### Stage 3 — Evidence Gatherer (the research agent)

- A Playwright-based agent that:
  1. Launches a headless browser.
  2. Navigates to the provider URL.
  3. Searches the page for the requested item/class/membership name.
  4. Extracts any visible price(s) near the item.
  5. Checks each website-verifiable checklist criterion (from config).
  6. **For each confirmed criterion**: injects a date-stamp overlay with ISO-8601 timestamp + URL, then takes a targeted screenshot.
  7. **Always**: takes a full-page capture (screenshot or PDF) of the page(s) reviewed as the "whole-site evidence."
  8. Returns `ChecklistResults` with per-item statuses and `EvidenceFile` references.

- **Date-stamping** (complies with Section 5 audit requirements):
  - Before each screenshot, inject a fixed-position `<div>` into the DOM showing:
    - `Captured: YYYY-MM-DD HH:MM:SS UTC`
    - `URL: <full URL>`
    - `Requirement: <checklist item ID>`
  - The overlay is styled to be unobtrusive but clearly legible and indelible in the screenshot.
  - Both whole-page and targeted captures receive this treatment.

### Stage 4 — Report Generator

- Jinja2 template renders to a standalone HTML file.
- Includes:
  - **Header**: participant name, provider, category, date of review.
  - **Rate comparison**: table showing form fee vs. website fee + verdict.
  - **Per-criterion table**: each website-verifiable item with status (Found / Not Found / Needs Review), evidence URL, screenshot thumbnail, and plain-language note.
  - **Internal items**: marked "Internal — not website-verifiable."
  - **Evidence gallery**: all full-page and targeted captures displayed with labels.
- Output: `reports/{ref_num}_report.html` + `reports/evidence/` folder.

---

## 4. Checklist Design (Config-Driven)

Each category gets a YAML file in `config/`. Example:

```yaml
category: community_class
fields:
  item_label: "Class Name"
  provider_label: "Name of Provider/Vendor"
  url_label: "Link to Webpage / Place of Publication"
  fee_label: "Fee per Session"

website_verifiable:
  - id: open_to_public
    label: Open to the broader public
    check_type: text_match
    keywords: ["open to the public", "open to all", "welcome everyone"]

  - id: published_fees
    label: Fees published on website
    check_type: price_presence

  - id: fees_identical_opwdd
    label: Fees identical for OPWDD and non-OPWDD individuals
    check_type: text_match
    keywords: ["no special pricing", "same price"]

  - id: subject_based
    label: Class is subject-based (art, dance, martial arts, etc.)
    check_type: text_match
    keywords: []  # verified by item name classification

  - id: no_college_credits
    label: Class does not give college credits
    check_type: text_match
    keywords: ["not for credit", "non-credit", "recreational"]

  - id: not_clinical
    label: Class is not clinical/therapy in nature
    check_type: text_match
    keywords: ["not therapeutic", "recreational"]

  - id: published_schedule
    label: Published schedule exists
    check_type: schedule_presence

  - id: fee_match
    label: Fee matches application
    check_type: price_compare

internal:
  - budget_approved
  - community_inclusion
  - health_safety_accommodation
  - increases_independence
  - exclusively_for_participant
  - duplicates_medicaid_waiver
  - duplicates_boe_services
  - setting_restricted_to_dd
  - run_by_opwdd_staff
  - located_on_opwdd_grounds
  - reimbursed_directly
```

New categories are added by dropping a new YAML file — no core code changes.

---

## 5. Evidence Date-Stamping Strategy (Section 5 Compliance)

To meet audit requirements for date-visible evidence:

1. **Overlay injection**: Before each capture, execute JavaScript in the page:
   ```js
   const div = document.createElement('div');
   div.id = 'opencode-evidence-overlay';
   div.style.cssText = 'position:fixed;bottom:10px;right:10px;...';
   div.innerHTML = `
     <span>Captured: ${new Date().toISOString()}</span><br>
     <span>URL: ${window.location.href}</span><br>
     <span>Requirement: ${requirementId}</span>
   `;
   document.body.appendChild(div);
   ```

2. **Two capture types per requirement**:
   - **Whole-page**: `page.screenshot({ fullPage: true })` — captures the full scrollable page context.
   - **Targeted**: `page.locator(element).screenshot()` — clips to the relevant DOM element showing the proof.
   - For very long pages, `page.pdf()` is used instead of a full-page screenshot (PDF preserves infinite-length content).

3. **Naming convention**: `{ref_num}_{requirement_id}_{ISO-date}.png`

4. **Integrity**: The overlay is rendered into the pixel output; no post-hoc watermarking that could be detached.

---

## 6. Risks & Edge Cases

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Top-level domain URL** (e.g., `graciebarra.com`) instead of a deep link | Agent must navigate the site; may not find the specific class | Playwright agent performs site search; if not found, mark "Needs Review" with note explaining the path taken |
| **Dynamic / JS-rendered content** | Static HTTP clients miss content | Playwright renders JS; wait for network idle + specific selectors |
| **Paywalled / gated pricing** | Fees behind login or "Contact Us" | Honestly report "Not Found"; do not fabricate |
| **CAPTCHAs / bot detection** | Site blocks the scraper | Use stealth Playwright config; rotate user-agents; fall back to human if blocked |
| **PDF/flyer-only pricing** | Fee schedule is a linked PDF, not on the page | Detect `.pdf` links and extract text from them |
| **Social media as provider page** | Unstructured, hard to scrape | Heuristic check; flag as "Needs Review" with note |
| **Checkbox extraction from scans** | Handwritten marks are hard to detect | pdfplumber for typed marks; LLM fallback; always show raw checkbox area to reviewer |
| **Ambiguous category / missing fields** | Cannot proceed | LLM asks clarifying questions; prompt user for missing info |
| **Price format variation** | `$80/30min`, `$30/session`, `$50/class` — hard to compare | LLM normalizes to a canonical `{amount, period}` struct; store both raw and normalized |
| **Appeals form** | Different logic: re-run community-class checks against a denial reason | Detect appeal form, load community class checklist, but add denial-reason context to the LLM prompt and evidence notes |
| **Rate limiting / blocking** | Multiple requests to same domain | Add configurable delay between navigations; respect `robots.txt` minimally |
| **Websites with no pricing at all** | Cannot verify fee | Mark "Not Found" — valid result per brief |

---

## 7. First Iteration (v1) Scope

**Supported categories (3 of 7):**
- Community Classes
- Coaching (for Parents/Spouse)
- Memberships (Health-Club / Organizational)

**Test data**: 3 provided sample PDFs.

**Interface**: CLI — `python verify.py <path-to-pdf>`

**Output**: HTML report in `reports/` + evidence screenshots in `reports/evidence/`.

**Out of scope for v1:**
- HRI, OTPS, Transition Program, Appeals categories
- Interactive plain-language Q&A loop (stage 3.5)
- Streamlit/Gradio web UI
- Docker containerization
- Production privacy controls (PHI masking)

---

## 8. Project Structure

```
trial/
├── PLAN.md                  # This file
├── README.md                # Project overview + setup
├── requirements.txt         # Python dependencies
├── config/                  # Checklist definitions (YAML)
│   ├── community_class.yaml
│   ├── coaching.yaml
│   └── memberships.yaml
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI entry point
│   ├── models.py            # Pydantic data models
│   ├── parser/              # PDF parsing (strategy pattern)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── community_class.py
│   │   ├── coaching.py
│   │   └── memberships.py
│   ├── extractor/           # LLM-based field extraction
│   │   ├── __init__.py
│   │   ├── chain.py
│   │   └── prompts.py
│   ├── gatherer/            # Playwright evidence gathering
│   │   ├── __init__.py
│   │   ├── browser.py
│   │   ├── scanner.py
│   │   └── stamper.py       # Date-stamp overlay injection
│   ├── reporter/            # Report generation
│   │   ├── __init__.py
│   │   ├── renderer.py
│   │   └── templates/
│   │       └── report.html.j2
│   └── utils/
│       ├── __init__.py
│       └── config_loader.py
├── samples/                 # Sample application PDFs
├── evidence/                # Output evidence captures
└── reports/                 # Generated reports
```

---

## 9. Dependencies (draft `requirements.txt`)

```
pymupdf
pdfplumber
langchain
langchain-openai
playwright
click
rich
jinja2
pydantic
pyyaml
```

---

## 10. Production Considerations (Not Implemented in v1)

- **PHI handling**: All data processed in-memory; no third-party API should receive real participant names. Use local LLMs (Ollama) if required.
- **Concurrency**: Asyncio for parallel evidence gathering across multiple checklist items.
- **Caching**: Cache scraped pages to avoid re-hitting the same URL within a session.
- **Retry + backoff**: Network resilience for flaky provider sites.
- **Docker**: Containerize for reproducible environments.
- **CI**: Lint (`ruff`), type-check (`mypy`), and run sample tests on commit.
