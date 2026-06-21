# Stage 4R - Filing Evidence Robustness

## Problem Statement

FinSight now produces polished, source-grounded research briefs with readable
financial presentation, deterministic period analysis, business overview
evidence, risk-factor evidence, LLM provider guardrails, compliance checks, and
report quality validation.

The next reliability bottleneck is SEC filing evidence extraction. Stage 4O
added initial Item 1 Business and Item 1A Risk Factors extraction, but the
current parser is intentionally narrow. Real 10-K filings can include table of
contents entries, HTML anchors, non-breaking spaces, inconsistent heading
punctuation, uppercase headings, `PART I` labels, repeated section names,
Item 1 and Item 1A heading variants, and different next-section boundaries.

Stage 4R strengthens filing evidence extraction so Company Overview and Risk
Factors remain grounded across more filing formats. The goal is not to parse
every historical filing perfectly. The goal is to improve coverage, avoid
cross-section leakage, and surface clear diagnostics when extraction is
uncertain or unavailable.

## Goals

- Improve Item 1 Business extraction across common 10-K heading variants.
- Improve Item 1A Risk Factors extraction across common 10-K heading variants.
- Avoid table-of-contents false positives where headings are listed without
  section body text.
- Avoid leaking Item 1A Risk Factors into Item 1 Business output.
- Avoid leaking Item 1B, Item 2, or later sections into Item 1A output.
- Preserve readable normalized section text.
- Add extraction quality diagnostics that explain success, fallback, or failure
  reasons.
- Preserve source IDs, filing metadata, character counts, extracted section
  names, and warning details in graph state and sources.
- Keep missing or uncertain evidence as warnings/limitations, not invented
  report prose.
- Keep normal tests deterministic with local fixtures and fake SEC clients.

## Non-Goals

- Do not add live SEC calls to normal unit tests.
- Do not use LLMs to parse, identify, repair, or summarize missing filing
  sections in this stage.
- Do not add external filing vendors or company metadata providers.
- Do not guarantee perfect extraction for every historical SEC filing format.
- Do not add new report sections or change the required 11-section structure.
- Do not change financial metric extraction or financial presentation.
- Do not add recommendations, ratings, price targets, or investment advice.
- Do not build a frontend, PDF export, or filing viewer in this stage.
- Do not store raw filing documents in persistence unless a later stage scopes
  that explicitly.

## Current Filing Architecture

The existing implementation includes:

- `find_latest_filing(submissions, form_type)` for latest 10-K and 10-Q
  metadata.
- `normalize_accession_number(accession_number)` for SEC document paths.
- `extract_business_section(filing_text)` for Item 1 Business.
- `extract_risk_factors_section(filing_text)` for Item 1A Risk Factors.
- Filing parser tests in `tests/test_filing_parser.py`.
- A sample 10-K excerpt fixture in `tests/fixtures/sample_10k_excerpt.txt`.
- Graph integration in `fetch_filing_text`.
- Graph state fields:
  - `filing_text`
  - `business_sections`
  - `business_overview`
  - `risk_factors`
  - `sources`
  - `warnings`

Stage 4R should build on these surfaces rather than replacing the filing
workflow.

## Input Contract

### Parser Input

The parser receives a raw latest 10-K primary document as text or HTML.

Supported input should include common variants such as:

```text
Item 1. Business
ITEM 1 BUSINESS
ITEM 1. BUSINESS
Item 1 - Business
Item 1: Business
PART I
ITEM 1. Business
ITEM 1A. Risk Factors
Item 1B. Unresolved Staff Comments
Item 2. Properties
```

HTML may include:

- tags around headings,
- `&nbsp;` entities,
- anchors,
- table rows,
- repeated table-of-contents references,
- inconsistent whitespace.

### Graph Input

The graph already has:

- `latest_10k`: latest 10-K metadata, or `None`,
- `filing_text`: full latest 10-K document text, or `None`,
- `sources`: source records including `latest_10k`,
- `warnings`: structured workflow warnings.

Stage 4R may add richer extraction diagnostics to parsed records or source
metadata, but it should not break existing graph state consumers.

## Output Contract

### Parser Output

Business extraction should return a structured object when confident:

```python
BusinessSection(
    item="1",
    section_label="Business",
    text="...",
)
```

Risk-factor extraction should return:

```python
RiskFactorsSection(
    item="1A",
    text="...",
)
```

The extracted text must:

- start after the selected section heading,
- stop before the next appropriate item heading,
- normalize HTML and whitespace into readable text,
- exclude table-of-contents heading lists,
- exclude the heading text itself from the section body,
- return `None` when the section cannot be confidently extracted.

### Diagnostics Output

Stage 4R should add extraction diagnostics without weakening existing outputs.
Diagnostics may include:

```python
{
    "status": "extracted" | "unavailable" | "ambiguous",
    "section": "Item 1 Business",
    "start_heading": "Item 1. Business",
    "end_heading": "Item 1A. Risk Factors",
    "text_character_count": 1234,
    "candidate_count": 2,
    "selection_reason": "selected longest body after heading",
    "warning_reason": None,
}
```

The exact shape can be refined during implementation, but diagnostics must be
structured and deterministic.

### Graph Output

When extraction succeeds:

- `business_sections` and `risk_factors` contain structured evidence records.
- `latest_10k` source metadata includes extracted sections.
- source metadata includes character counts and extraction status.
- final reports continue to use deterministic business overview and risk
  evidence.

When extraction fails or is ambiguous:

- graph execution should continue where possible,
- warnings should be structured,
- final reports should surface limitations,
- missing evidence must not be replaced with invented facts,
- report quality validation should still run when a final report exists.

## Required Boundary Rules

- Business extraction must not include Item 1A Risk Factors body text.
- Business extraction must stop before Item 1A, Item 1B, Item 2, or another
  confident next section when Item 1A is unavailable.
- Risk Factors extraction must not include Item 1 Business body text.
- Risk Factors extraction must stop before Item 1B, Item 2, or another
  confident next section.
- Table-of-contents rows should not be selected as section bodies.
- If there are multiple candidate headings, prefer the candidate with a
  plausible body and next-section boundary over a short table-of-contents
  occurrence.
- If no candidate has a plausible body, return `None` with diagnostics rather
  than returning noisy text.

## Required Source and Citation Rules

- Business-section evidence from the latest 10-K uses source ID `latest_10k`.
- Risk-factor evidence from the latest 10-K uses source ID `latest_10k`.
- Company Overview should cite `[latest_10k]` only when business evidence is
  actually used.
- Risk Factors should cite `[latest_10k]` when risk evidence or risk themes are
  actually used.
- Missing section evidence should not create fake citations.
- Source metadata should accurately list extracted sections and extraction
  status.

## Required Language Rules

Reports and warnings must avoid:

- invented filing facts,
- unsupported company descriptions,
- raw copied filing sections in final reports,
- investment advice,
- scaffold language,
- overconfident claims when extraction is ambiguous.

Acceptable limitation language examples:

- "Item 1 Business could not be confidently extracted from the latest 10-K."
- "Item 1A Risk Factors could not be confidently extracted from the latest
  10-K."
- "The filing parser found multiple heading candidates and did not select a
  business section because no candidate had a plausible body."

## Test-Driven Workflow for 4R

Each implementation slice after 4R-0 must follow this loop:

1. Add or update tests that express the next acceptance criterion.
2. Run the targeted tests and confirm they fail for the intended reason.
3. Implement the smallest production-quality change.
4. Re-run the targeted tests and confirm they pass.
5. Run broader verification when the slice touches graph behavior, report
   behavior, or documentation.

Normal tests must remain deterministic and must not call real SEC or real LLM
services.

## Acceptance Criteria

### 4R-0: Spec

- `docs/specs/4R-filing-evidence-robustness.md` exists.
- The spec defines problem statement, goals, non-goals, current architecture,
  input contract, output contract, diagnostics, boundary rules, source/citation
  rules, language rules, TDD workflow, acceptance criteria, test plan, and
  definition of done.
- No parser, graph, report generator, API, docs, or test behavior changes are
  made in this slice.

### 4R-1: Parser Fixture Expansion

- Add failing parser tests and local fixtures for common heading variants.
- Fixtures cover uppercase headings, punctuation variants, `PART I`, HTML tags,
  non-breaking spaces, repeated heading references, and table-of-contents noise.
- Current simple fixture behavior remains covered.
- Tests prove the parser returns `None` when a section is missing.

### 4R-2: Boundary Detection Hardening

- Add failing tests for cross-section leakage.
- Business extraction excludes Item 1A Risk Factors and later sections.
- Risk extraction excludes Item 1 Business, Item 1B, Item 2, and later sections.
- Multiple heading candidates choose the most plausible section body.
- Table-of-contents headings are skipped when a later full section exists.
- Empty or implausibly short extracted bodies return `None` rather than noisy
  output.

### 4R-3: Extraction Diagnostics

- Add failing tests for structured extraction diagnostics.
- Parser or graph diagnostics identify extracted, unavailable, and ambiguous
  section outcomes.
- Diagnostics include section label, candidate count, text character count
  where available, and deterministic warning reason where unavailable.
- Existing `business_section_unavailable` and `risk_factors_unavailable`
  warnings remain structured.
- Source metadata records extracted sections and extraction status accurately.

### 4R-4: Graph Proof Across Filing Fixtures

- Add graph-level tests with multiple fake SEC clients or fixture documents.
- Normal graph runs still produce final reports with required disclaimer,
  source IDs, compliance status, and report quality status.
- Successful extraction records both Item 1 Business and Item 1A Risk Factors.
- Missing or ambiguous extraction produces warnings and limitations without
  inventing business or risk content.
- LLM fallback behavior and diagnostics remain unchanged.

### 4R-5: Docs and Verification

- README and agent-facing docs document improved filing extraction robustness
  after behavior is implemented.
- Documentation explains that parsing is deterministic and fixture-tested.
- Documentation explains limitations for ambiguous or unavailable filing
  sections.
- Focused parser, graph, and docs tests pass.
- Full verification passes:

```powershell
uv run pytest
uv run ruff check .
```

## Test Plan

### Parser Tests

- Extract Item 1 Business from uppercase headings.
- Extract Item 1 Business from punctuation variants.
- Extract Item 1 Business when preceded by `PART I`.
- Extract Item 1 Business from HTML with non-breaking spaces.
- Skip table-of-contents `Item 1` and `Item 1A` references.
- Extract Item 1A Risk Factors from uppercase headings.
- Extract Item 1A Risk Factors from punctuation variants.
- Stop Item 1A before Item 1B or Item 2.
- Return `None` when Item 1 Business is missing.
- Return `None` when Item 1A Risk Factors is missing.
- Return `None` for ambiguous or implausibly short candidate bodies.

### Diagnostics Tests

- Successful business extraction reports `status="extracted"`.
- Successful risk extraction reports `status="extracted"`.
- Missing business extraction reports a deterministic warning reason.
- Missing risk extraction reports a deterministic warning reason.
- Ambiguous headings report candidate counts and a warning reason.
- Source metadata includes extracted section names only for sections actually
  extracted.

### Graph Tests

- Graph run with robust business/risk fixture extracts both sections.
- Graph run with table-of-contents noise extracts the actual body sections.
- Graph run with missing business section still produces a safe report and
  limitation.
- Graph run with missing risk section still produces a safe report and
  limitation.
- Graph run with ambiguous section headings does not invent evidence.
- Report quality still passes when enough SEC-derived evidence exists.

### Documentation Tests

- README documents deterministic filing extraction robustness.
- README documents limitations for unavailable or ambiguous filing sections.
- Agent docs identify Stage 4R status and remaining work.

## Definition of Done

Stage 4R is done when:

- The 4R spec exists and matches implemented behavior.
- Parser fixtures and tests are written before parser implementation changes.
- Boundary detection tests are written before parser hardening.
- Diagnostics tests are written before diagnostics implementation.
- Graph proof tests cover successful, missing, and ambiguous section extraction.
- Business and risk extraction remain source-grounded and deterministic.
- Final reports avoid raw filing text and invented business or risk facts.
- Missing or ambiguous filing evidence appears as warnings or limitations.
- LLMs are not used for filing parsing or section repair.
- README and agent docs reflect completed behavior.
- `uv run pytest` and `uv run ruff check .` pass.
