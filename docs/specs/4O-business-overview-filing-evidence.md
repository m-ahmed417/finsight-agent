# Stage 4O - Business Overview and Filing Evidence

## Problem Statement

Stage 4N made FinSight reports production-style, source-grounded, and
scaffold-free. The Company Overview section is now safe and honest, but it is
still intentionally shallow because the workflow does not extract real business
description evidence from SEC filings.

The latest 10-K usually contains an Item 1 / Business section that can provide
grounded context about what the company does, its products or services,
segments, customers, markets, distribution, and operating model. FinSight should
extract this filing evidence and use it to improve the Company Overview without
inventing business facts or copying raw filing text into the final report.

## Goals

- Extract latest 10-K Item 1 / Business text separately from Item 1A / Risk
  Factors.
- Preserve source metadata for business-section evidence.
- Add typed graph state for extracted business evidence.
- Add deterministic business overview synthesis from structured filing
  evidence.
- Feed business overview evidence into report generation.
- Keep Company Overview neutral, citation-aware, and honest about limitations.
- Avoid copying raw filing text into the final report.
- Preserve the 11-section report structure and Stage 4N quality guarantees.
- Keep normal tests deterministic with fixtures and fake SEC clients.

## Non-Goals

- Do not add live SEC calls to normal unit tests.
- Do not use an LLM to extract or summarize Item 1 in this stage.
- Do not introduce external company metadata providers.
- Do not infer facts that are not present in extracted filing evidence.
- Do not change financial metric calculations.
- Do not add recommendations, ratings, target prices, or investment advice.
- Do not add a frontend, PDF export, or report viewing UI.
- Do not build robust parsing for every historical filing format in this first
  slice; implement a tested, defensible parser that can improve iteratively.

## Input Contract

### Filing Parser Input

The filing parser receives raw filing document text or HTML from the latest
10-K primary document.

The parser must support plain-text fixtures such as:

```text
Item 1. Business
...
Item 1A. Risk Factors
...
Item 1B. Unresolved Staff Comments
```

The parser should tolerate common heading variants where practical, including
case differences and extra whitespace.

### Graph Input

The graph already has:

- `latest_10k`: latest 10-K metadata, or `None`.
- `filing_text`: full latest 10-K document text, or `None`.
- `sources`: source records including `latest_10k`.
- `warnings`: structured workflow warnings.

Stage 4O should add business-section evidence to graph state while preserving
existing risk-factor extraction behavior.

### Report Input

Report generation should receive structured business overview evidence such as:

- `source_id`
- `source_type`
- `form`
- `filing_date`
- `accession_number`
- `source_url`
- `source_ids`
- `section`
- `section_label`
- extracted text or a deterministic summary artifact
- text character counts
- extraction timestamp

Raw extracted Item 1 text may be stored in graph state for diagnostics, but it
must not be copied directly into the final report.

## Output Contract

### Parser Output

The parser should return a structured object for Item 1 / Business when
available:

```python
BusinessSection(
    section="Item 1",
    section_label="Business",
    text="...",
)
```

The extracted text must:

- start after the Item 1 / Business heading,
- stop before Item 1A / Risk Factors or the next appropriate filing section,
- not include the Item 1A risk-factor body,
- be normalized to readable text,
- return `None` when no business section can be confidently extracted.

### Graph Output

Graph state should include:

```python
business_sections: list[dict[str, Any]]
business_overview: dict[str, Any] | None
```

`business_sections` stores extracted Item 1 evidence. `business_overview`
stores deterministic, report-ready overview content or diagnostics derived from
the evidence.

When Item 1 extraction succeeds, update the `latest_10k` source metadata with
`Item 1 Business` in `extracted_sections`.

When Item 1 extraction fails, add a structured warning:

```json
{
  "code": "business_section_unavailable",
  "message": "Item 1 business section could not be extracted.",
  "severity": "warning",
  "details": {
    "source_id": "latest_10k"
  }
}
```

### Report Output

The Company Overview section should:

- cite `[latest_10k]` when it uses latest 10-K business evidence,
- mention filing metadata such as form, filing date, or accession number when
  available,
- use only deterministic structured evidence,
- avoid raw copied filing text,
- avoid invented products, services, markets, or business model claims,
- surface missing business evidence as a limitation or careful overview
  constraint.

The report must continue to pass Stage 4N quality validation when enough
SEC-derived evidence exists.

## Required Source and Citation Rules

- Business-section evidence from the latest 10-K uses source ID `latest_10k`.
- If source metadata is available, citations must refer to known source IDs.
- Company Overview claims based on business-section evidence must cite
  `[latest_10k]`.
- Sources Used should show that the latest 10-K source includes Item 1 Business
  in `extracted_sections` when extraction succeeds.
- Missing Item 1 evidence must not create fake citations or invented prose.

## Required Language Rules

Company Overview must avoid:

- raw copied filing paragraphs,
- marketing-style promotion,
- investment advice,
- invented product or market claims,
- scaffold language,
- apologies for implementation limitations.

Acceptable language examples:

- "The latest 10-K business section was available for this run and is used as
  source evidence for the company overview. [latest_10k]"
- "The available filing evidence identifies the latest 10-K as the business
  context source; this report does not add external company descriptions.
  [latest_10k]"
- "Item 1 business text could not be extracted in this run, so the overview is
  limited to resolved company identity and available SEC metadata."

## Limitations Behavior

- If Item 1 extraction fails, add a warning and surface it in report
  limitations.
- If Item 1 extraction succeeds but deterministic synthesis is intentionally
  conservative, state the scope plainly.
- Do not replace missing business evidence with broad public-knowledge claims.
- Do not let missing business evidence prevent financial, risk, compliance, or
  quality validation from running when the rest of the workflow can continue.

## Acceptance Criteria

### 4O-0: Spec

- `docs/specs/4O-business-overview-filing-evidence.md` exists.
- The spec defines problem statement, goals, non-goals, input contract, output
  contract, source/citation rules, language rules, limitations behavior,
  acceptance criteria, test plan, and definition of done.
- No parser, graph, generator, or API behavior changes are made in this slice.

### 4O-1: Filing Parser TDD

- Add failing tests in `tests/test_filing_parser.py`.
- Parser extracts Item 1 / Business from a fixture that also contains Item 1A.
- Parser output excludes Item 1A Risk Factors and later sections.
- Parser returns `None` when Item 1 / Business is missing.
- Existing Item 1A risk-factor extraction tests continue to pass.

### 4O-2: Graph State and Extraction Integration

- Add `business_sections` and `business_overview` to `FinSightState`.
- Initialize, preserve, and persist these fields through graph state updates as
  appropriate.
- `fetch_filing_text` extracts Item 1 Business and Item 1A Risk Factors from the
  same latest 10-K document.
- Latest 10-K source metadata records both extracted sections when available.
- Missing business section creates a warning but does not stop the workflow.

### 4O-3: Deterministic Business Overview Synthesis

- Add a deterministic service that creates report-ready business overview
  evidence from extracted business sections.
- The service must not copy raw Item 1 text into final report prose.
- The service must preserve `source_ids=["latest_10k"]`.
- Missing evidence produces a clear limitation or diagnostic output.

### 4O-4: Report Generator Integration

- `generate_research_report` accepts business overview evidence.
- Company Overview cites `[latest_10k]` when business evidence is used.
- Company Overview remains professional and scaffold-free.
- Raw Item 1 text does not appear in the final report.
- Sources Used lists Item 1 Business extraction metadata.
- Limitations include missing business-section warnings when applicable.

### 4O-5: Graph Proof, Docs, and Verification

- Graph-level tests prove a normal SEC-evidence run extracts business evidence
  and uses it in the final report.
- Normal graph runs still end with `report_quality_status == "passed"` when
  enough SEC-derived evidence exists.
- LLM fallback behavior remains unchanged.
- README and agent docs are updated after behavior is implemented.
- Full verification passes:

```powershell
uv run pytest
uv run ruff check .
```

## Test Plan

### Parser Tests

- Extract Item 1 Business from `sample_10k_excerpt.txt`.
- Assert extracted business text includes expected business content.
- Assert extracted business text excludes Item 1A and Item 1B content.
- Return `None` when Item 1 Business is absent.
- Preserve existing Item 1A Risk Factors extraction behavior.

### Graph Tests

- Successful graph run includes `business_sections`.
- Successful graph run includes `business_overview`.
- Latest 10-K source metadata includes `Item 1 Business`.
- Missing Item 1 creates `business_section_unavailable` warning.
- Existing filing-text-unavailable behavior still works.
- Existing LLM skipped/fallback call events remain unchanged.

### Business Overview Synthesis Tests

- Business overview synthesis produces deterministic, citation-ready output.
- Output includes source IDs from latest 10-K evidence.
- Output does not include raw filing text.
- Missing business evidence produces a limitation-friendly result.

### Report Generator Tests

- Company Overview uses business overview evidence when provided.
- Company Overview cites `[latest_10k]`.
- Company Overview does not copy raw Item 1 text.
- Reports still pass quality validation with full evidence.
- Missing business evidence appears in Limitations through workflow warnings.

### Docs Tests

- README documents business overview grounding once behavior is implemented.
- Agent docs identify Stage 4O status and remaining work.

## Definition of Done

Stage 4O is done when:

- The 4O spec exists and matches implemented behavior.
- Parser tests are written before parser changes and pass after implementation.
- Graph/state tests are written before graph changes and pass after
  implementation.
- Business overview synthesis tests are written before synthesis changes and
  pass after implementation.
- Report generator tests are written before report changes and pass after
  implementation.
- Graph proof confirms normal runs use Item 1 evidence and still pass report
  quality validation.
- Final reports remain neutral, source-grounded, citation-aware, and
  research-only.
- Raw filing text is not copied into final reports.
- Missing Item 1 data is surfaced as warnings or limitations.
- README and agent docs reflect completed behavior.
- `uv run pytest` and `uv run ruff check .` pass.
