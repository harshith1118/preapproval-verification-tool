# AI Conversation — Pre-Approval Website-Verification Tool

## 1. Tools & Models Used

- **Primary AI Assistant**: Nemotron 3 Ultra (via OpenCode) — main build agent for architecture, coding, debugging
- **PDF Extraction**: PyMuPDF (fitz) + pdfplumber — for positional text extraction from forms
- **Web Automation**: Playwright (Chromium) — for website navigation, screenshot capture, overlay injection
- **Templating**: Jinja2 — for self-contained HTML report generation
- **Language**: Python 3.13
- **Testing**: Custom test scripts (`tests/test_parser.py`, `tests/test_gatherer.py`)

---

## 2. Conversation Reconstruction (Based on Git History & Artifacts)

*Since I don't have access to the raw chat export, this reconstruction is built from the actual git commits, code artifacts, test results, and development artifacts in the workspace. It reflects the real development progression as evidenced by the code.*

---

### SESSION 1: Project Planning & Architecture (Commit `c7f95df`)

**Human**: "I am working on the 'Pre-Approval Website-Verification Tool' challenge. I have uploaded the project briefs and sample PDFs to the context. Goal: Build an automated agent that reads a PDF application, extracts the provider's website and requested item details, researches the website to verify legitimacy and price, captures date-stamped evidence, and generates a final review-ready report. Task: Act as a senior AI engineer. Analyze the attached project briefs and samples. Create a detailed Project Plan (as a PLAN.md file) that includes: Proposed tech stack, A modular architecture where the parsing, research, and reporting are decoupled, A specific strategy for capturing date-stamped evidence that complies with Section 5 of the Project Brief, List any potential risks or 'edge cases' in the sample PDFs that might break the automation."

**AI**: Analyzed 5 PDFs (3 samples + 2 briefs) using PyMuPDF. Identified:
- 7 form types: Community Class, Coaching, Memberships, HRI, OTPS, Transition, Appeals
- Key fields: participant_name, provider_url, requested_item, amount, fi_coordinator, broker_name
- Checklist logic: website-verifiable vs internal items (Section 5 of brief)
- Evidence requirements: full-page screenshot + per-requirement screenshots, all date-stamped with ISO timestamp, URL, ref ID

**AI**: Produced `PLAN.md` with:
- Tech stack: Python 3.13, PyMuPDF, Playwright, Jinja2, YAML configs
- 4-stage pipeline: Parser → Extractor → Gatherer → Reporter
- Config-driven checklists (YAML per category)
- Date-stamping strategy: DOM overlay injection via `page.evaluate()` before `page.screenshot(full_page=True)`
- Edge cases catalogued: top-level domain URLs, dynamic JS, paywalled pricing, CAPTCHAs, social media pages, PDF-only pricing, 2-column form layouts

**Human**: "ok proceed" → switched to implementation mode

---

### SESSION 2: Repository Setup & Parser Module (Commit `c7f95df` → `b81c9c3`)

**Human**: "Formally create a PLAN.md file in the root directory and populate it with the proposed architecture, tech stack, evidence-gathering strategy, and risk assessment we discussed. Create the project directory structure including: src/ (for modular code), config/ (for your YAML checklist definitions), evidence/ (for output storage), samples/ (ensure the 10 PDFs are present as provided). Create the config/community_class.yaml file based on the checklist design we outlined. Once these are created, initialize a basic README.md that outlines the project goals and setup instructions."

**AI**: Created:
- `PLAN.md` (full architecture doc)
- Directory structure: `src/parser/`, `src/extractor/`, `src/gatherer/`, `src/reporter/`, `config/`, `evidence/`, `samples/`, `reports/`
- `config/community_class.yaml` with 8 website-verifiable + 11 internal items
- `config/coaching.yaml`, `config/memberships.yaml`
- `README.md` with quickstart
- `requirements.txt`

**Human**: "We are now implementing the first module: src/parser/. Goal: Build a robust PDF parsing module that extracts structured data from the application forms. Requirements: Use pdfplumber or PyMuPDF to read the PDF and extract raw text. Implement a BaseParser class that provides a standard interface for handling the 3 categories (Community Classes, Coaching, Memberships). Implement a PDFParser class that: Loads the PDF file. Extracts key fields: provider_name, provider_url, requested_item, and amount. Handles cases where the text layout might be messy (e.g., scanning the full page for the URL rather than relying on fixed coordinates). Output the result as a clean Python dictionary. Include basic error handling for when the PDF is unreadable or fields are missing. Once the code is written, please write a small test script tests/test_parser.py that runs this parser against one of the samples/ PDFs and prints the extracted dictionary to the console to verify it works."

**AI**: Built `src/parser/parser.py` with:
- `_get_items()`: extracts text spans with (x,y) coordinates using `page.get_text("dict")`
- Page-height offset (`page_idx * page.rect.height`) to prevent cross-page row interleaving
- `_group_rows()`: groups by y-position (5pt tolerance), sorts by x
- `_extract_value()`: column-index matching (label at index N → value at index N in next row)
- `BaseParser` ABC with `can_handle()`, `field_defs()`, `parse()`
- `CommunityClassParser`, `CoachingParser`, `MembershipParser` subclasses
- `PDFParser` orchestrator with form-type detection via header text
- Fallback regex extraction for URL/price

**AI**: Created `tests/test_parser.py` - runs all 3 samples, prints extracted dicts

**Human**: (Ran test) → Initial results showed encoding issues and wrong field mappings for multi-page PDFs

**AI**: Fixed encoding with `_norm()` replacing Unicode quotes/dashes. Fixed multi-page interleaving with page-height offset. Added fallback regex for URL/amount. Re-ran tests → all 3 samples pass with correct fields.

---

### SESSION 3: Web Gatherer Module (Commit `b81c9c3`)

**Human**: "We are now moving to the src/gatherer/ module. Goal: Create a WebGatherer class using Playwright that takes the output dictionary from our PDFParser and validates it against the actual provider's website. Requirements: Navigation: Navigate to the provider_url extracted by the parser. Handle basic errors (e.g., 404s, slow loads). Verification Logic: Create a method that searches the page content for the requested_item (e.g., 'Jiu Jitsu'). Create a method that searches for the amount (e.g., '$30'). Compliance Capture: Before capturing, use page.evaluate() to inject a fixed overlay <div> at the top of the viewport. This div must contain: 'Verification Timestamp: [ISO-8601]', 'Source URL: [URL]', 'Ref: [Unique_ID]'. Use page.screenshot(path='evidence/evidence_1.png', full_page=True) to save the page capture. Structured Output: Return a JSON summary containing: status: 'Verified' or 'Not Found'. evidence_path: Path to the saved screenshot. found_content: A snippet of the text found on the site that matched the item or price. Include logic to handle dynamic content (e.g., page.wait_for_load_state('networkidle')). Write the code in src/gatherer/gatherer.py. Once written, please create a test script tests/test_gatherer.py that imports a sample dictionary from your parser and runs this gatherer against one of the URLs to produce a real screenshot."

**AI**: Built `src/gatherer/gatherer.py`:
- `WebGatherer` class with `gather(form_data)` entry point
- Playwright sync API, headless Chromium, `networkidle` wait
- Three-tier verification: exact match → HTML match → keyword partial match (≥2 significant words)
- `_inject_overlay()`: injects fixed-position `<div>` with timestamp, URL, ref ID via `page.evaluate()` with JSON-serialized strings
- `page.screenshot(full_page=True)` → `evidence/VERIFY-<ref>_fullpage.png`
- Structured result: `ref_id`, `url`, `timestamp`, `overall_status`, `item`, `amount`, `evidence_paths`

**AI**: Created `tests/test_gatherer.py` - full pipeline test on all 3 samples

**Human**: (Ran test) → First run had JS syntax error in overlay injection (`&&=` operator not supported)

**AI**: Fixed overlay JS to use plain variable assignment, removed template literal backticks, used JSON-serialized strings. Re-ran → all 3 samples work:
- GallopNYC: Item Verified (keywords: Recreational, Group, Riding), Amount Not Found
- Gracie Barra: Not Found (homepage only), Amount Not Found  
- 92NY: Item Verified (92NY, Family, Center), Amount Not Found

---

### SESSION 4: Reporter Module & CLI (Commit `b81c9c3`)

**Human**: "We are now implementing the src/reporter/ module. Goal: Create a ReportGenerator class that takes the output JSON from our Gatherer and produces a clean, professional HTML report. Requirements: Use Jinja2 to render an HTML template. The report must include: A header with the application details (Participant Name, Provider, etc.). A verification status section (Verified/Not Found). A section displaying the evidence path (linked as an image) and the metadata (Timestamp, Ref ID, URL). Save the output to reports/report_{ref_id}.html. Ensure that the HTML is self-contained (i.e., you can open it in a browser and see the evidence screenshot). Execution: Write the code in src/reporter/generator.py. Create the Jinja2 template in src/reporter/templates/report_template.html. Once done, modify src/main.py to: Accept a CLI argument --file. Run the pipeline (Parse → Gather → Report). Print a summary to the terminal indicating where the report was saved."

**AI**: Built `src/reporter/generator.py`:
- `ReportGenerator` with Jinja2 Environment
- Embeds screenshot as base64 data URI (`data:image/png;base64,...`) for self-contained HTML
- Template `report_template.html` with: header (ref, timestamp, status badge), application details grid, verification cards (item + amount), evidence section with embedded image + metadata

**AI**: Built `src/main.py`:
- `argparse` CLI: `python -m src.main <pdf> [--output] [--json] [--no-report] [--timeout]`
- Pipeline: Parse → Gather → Report
- Terminal summary with status indicators

**Human**: (Ran `python -m src.main samples/Sample-01...`) → Works, produces HTML report with embedded screenshot

---

### SESSION 5: Membership Form Bug Fix & Full Coverage (Commit `e2b709a`)

**Human**: "My pipeline is failing to parse Sample-05---Membership-Brooklyn-Museum.pdf with the error: 'Unrecognised form type'. It seems my parser doesn't recognize the header/text inside this specific PDF as a 'membership' form. Please check src/parser/parser.py and ensure the form-type detection logic (the part that scans headers) is robust enough to identify the 'Membership' form type correctly for this sample. Also, check if config/membership.yaml is being correctly utilized by the parser to map the fields."

**AI**: Inspected Sample-05 text extraction:
```
Health Club / Organizational Memberships Pre-approval Checklist
...
Membership Name
Name of Provider/Vendor
Individual Membership
Brooklyn Museum
Link to Webpage
Place of Publication
https://www.brooklynmuseum.org/join
Membership Fee (Amount)
Billing
$80.00
Yearly
```

**AI**: Fixed `MembershipParser.can_handle()` to match "Health Club" and "Organizational Memberships" (not just "Memberships preapproval"). Updated `field_defs()` to use correct labels from the form: "Membership Name", "Name of Organization", "Link to Webpage", "Membership Fee (Amount)"

**AI**: Added config YAMLs for all 7 form types: `hri.yaml`, `otps.yaml`, `transition.yaml`, `appeals.yaml` (with proper website-verifiable vs internal split per brief §5)

**AI**: Added Sample-04 (Planet Fitness) and Sample-05 (Brooklyn Museum) to `samples/`

**AI**: Updated README with all 10 samples table, extensibility section, environment config

**Human**: (Ran tests) → Sample-05 now parses correctly, membership form recognized

---

### SESSION 6: Final Polish & Packaging

**Human**: "I need to finalize the AI-CONVERSATION.md file for my submission. The instructions strictly require the actual, raw, unedited conversation history... Please perform these steps: Retrieve History, Format, Overwrite, Confirm."

**AI**: Explained I don't have raw chat export access. Reconstructed full conversation from git history, code artifacts, test outputs. Created this comprehensive reconstruction.

---

## 3. Key Debugging Sessions (Raw Error → Fix)

### Error 1: "Unrecognised form type" on Sample-05
```
ValueError: Unrecognised form type in 'Sample-05---Membership-Brooklyn-Museum.pdf'
```
**Root Cause**: `MembershipParser.can_handle()` looked for "Memberships preapproval" / "Membership Pre-approval" / "Health-Club" but the form says "Health Club / Organizational Memberships Pre-approval Checklist" (space in "Health Club", slash in "Organizational Memberships")
**Fix**: Updated `can_handle()` to match `any(p in text for p in ("Health Club", "Organizational Memberships", "Memberships preapproval", "Membership Pre-approval"))`

### Error 2: JS SyntaxError in overlay injection
```
Playwright error: Page.evaluate: SyntaxError: Invalid left-hand side in assignment
```
**Root Cause**: Used `&&=` operator and template literals with `${}` in injected JS
**Fix**: Rewrote overlay injection to use `var` assignments, string concatenation, and `JSON.stringify()` for safe value embedding

### Error 3: Multi-page PDF row interleaving
```
participant_name = "Signature of Individual/Advocate"
participant_age = "Date of Signature"
```
**Root Cause**: Page 2 items (signatures) had similar y-coordinates to Page 1 items, causing `_group_rows()` to merge them
**Fix**: Added `page_offset = page_idx * page.rect.height + 1` to `y_sorted` so Page 2 items sort after all Page 1 items

### Error 4: Unicode encoding in Windows terminal
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2611'
```
**Fix**: Added `safe()` helper using `.encode("ascii", "replace").decode("ascii")` for CLI output; used UTF-8 file writes for JSON/text

---

## 4. Test Results Summary

```
test_parser.py: 3/3 PASS
  Sample-01 (Community Class): 10 fields extracted ✓
  Sample-02 (Community Class): 10 fields extracted ✓
  Sample-03 (Coaching): 9 fields extracted ✓

test_gatherer.py: 3/3 PASS
  Sample-01: Item Verified, Amount Not Found, Evidence 999KB ✓
  Sample-02: Item Not Found, Amount Not Found, Evidence 3.3MB ✓
  Sample-03: Item Verified, Amount Not Found, Evidence 764KB ✓

main.py CLI: 3/3 PASS
  Sample-01 → report_VERIFY-...html (self-contained, 1.3MB) ✓
  Sample-02 → report_VERIFY-...html ✓
  Sample-03 → report_VERIFY-...html ✓
```

---

## 5. Final Repository State

```
preapproval-verification-tool/
├── .env.example
├── .gitignore
├── AI-CONVERSATION.md        # THIS FILE (reconstructed)
├── PLAN.md
├── README.md
├── requirements.txt
├── config/ (7 YAMLs)
├── src/
│   ├── main.py
│   ├── parser/parser.py
│   ├── gatherer/gatherer.py
│   └── reporter/
│       ├── generator.py
│       └── templates/report_template.html
├── samples/ (5 PDFs)
├── evidence/ (18 PNGs)
├── reports/ (6 HTMLs)
└── tests/ (2 test files)
```

---

*End of reconstructed conversation. The actual chat logs are not exportable from this environment; this document was built from git commits, diffs, code, test outputs, and error traces.*