# Stage 4S - Report Citation Audit and Quality Details

## Problem Statement

FinSight now produces source-grounded reports with deterministic financial
presentation, robust latest 10-K filing extraction, report quality validation,
compliance checks, and optional LLM-assisted drafting behind deterministic
fallbacks.

The next trust bottleneck is explainability of report quality. The current
validator can warn when a required section is missing, when required sections
lack citations, and when a report cites an unknown source ID. That is useful,
but it is still too coarse for debugging, API clients, future UI display, and
agent evaluation. A user or developer should be able to inspect which report
sections were audited, which citations appeared in each section, which source
IDs were known, and why the report passed or produced warnings.

Stage 4S adds deterministic citation-audit and quality-detail surfaces around
the existing report validator. The goal is not to create a subjective report
grader. The goal is to make source grounding inspectable, structured, stable,
and testable.

## Goals

- Add a deterministic report citation audit that extracts citations by report
  section.
- Track known, unknown, and missing required citations in structured data.
- Preserve the existing `report_quality_status` contract.
- Preserve existing warning codes while adding richer details where useful.
- Make section-level citation coverage available to graph and API consumers.
- Prove that valid generated reports pass quality validation with citation
  details.
- Prove that missing or unknown citations are reported with precise section
  details.
- Prove that unsafe LLM report drafts cannot bypass citation validation.
- Keep all quality checks deterministic and independent of model output prose
  style.
- Keep normal tests deterministic with local fixtures and fake LLM/SEC clients.

## Non-Goals

- Do not add a subjective investment-quality score.
- Do not add buy/sell/hold language, ratings, price targets, forecasts, or
  personalized portfolio guidance.
- Do not use an LLM to judge citation quality, repair missing citations, or
  decide whether a source supports a claim.
- Do not change the required 11-section report structure.
- Do not add new SEC data sources or external metadata providers.
- Do not change deterministic financial calculations.
- Do not require live SEC or live LLM access in normal tests.
- Do not build a frontend, charting UI, PDF export, or report viewer in this
  stage.
- Do not introduce a database migration unless an implementation slice proves
  that explicit persisted quality-detail fields are necessary.

## Current Report Quality Architecture

The existing implementation includes:

- Report generation in
  `src/finsight_agent/app/services/report_generator.py`.
- Report quality validation in
  `src/finsight_agent/app/services/report_validator.py`.
- Required report sections defined in `REQUIRED_SECTIONS`.
- Citation-required sections defined in `CITATION_REQUIRED_SECTIONS`.
- Weak/scaffold language checks.
- Missing required citation warnings.
- Unknown source ID citation warnings when `sources` are provided.
- Compliance checks for financial-advice language.
- Graph-level validation in the `validate_report` node.
- Graph state field:
  - `report_quality_status`
- Structured warnings with code `report_quality_warning`.
- API exposure of `report_quality_status`.

Stage 4S should extend these surfaces rather than replacing the report
validator.

## Input Contract

### Citation Audit Input

The citation audit receives:

- `report`: final report Markdown, or `None`.
- `sources`: optional list of source dictionaries.
- required section headings from the existing 11-section report structure.
- citation-required section headings from the existing validator contract.

Known source IDs come from source records with a non-empty `source_id`.

Citation syntax remains the existing source-id format:

```text
[sec_company_facts]
[latest_10k]
```

The audit should not treat arbitrary bracketed prose as source IDs unless it
matches the established source ID pattern.

### Graph Input

The graph already has:

- `final_report`
- `sources`
- `warnings`
- `report_quality_status`
- `llm_report_sections`
- `compliance_status`

Stage 4S may add a typed graph-state field such as `citation_audit` or
`report_quality_details`, but it should not remove or rename existing fields.

## Output Contract

### Citation Audit Output

The citation audit should produce deterministic structured data. The exact
model can be refined during implementation, but it should include:

```python
{
    "status": "passed" | "warning",
    "known_source_ids": ["latest_10k", "sec_company_facts"],
    "sections": [
        {
            "heading": "## 4. Financial Performance",
            "requires_citation": True,
            "present": True,
            "citations": ["sec_company_facts"],
            "known_citations": ["sec_company_facts"],
            "unknown_citations": [],
            "missing_required_citation": False,
        }
    ],
    "missing_required_sections": [],
    "unknown_citations": [],
    "sections_missing_required_citations": [],
}
```

Rules:

- Preserve report section order.
- Deduplicate citations in first-seen order.
- Include only citations that appear inside each section body.
- Record missing sections separately from present sections without body text.
- Mark required citation sections when no citation is found.
- Mark citations unknown when they do not map to known `source_id` values.
- Continue to allow sections that intentionally do not require citations.

### Report Quality Output

Report quality validation should keep returning:

```python
ReportQualityResult(
    status=ReportQualityStatus.PASSED | ReportQualityStatus.WARNING,
    warnings=[...],
)
```

Stage 4S may add an optional structured field such as:

```python
details={
    "citation_audit": {...},
    "missing_sections": [...],
    "weak_sections": [...],
    "unsafe_language_terms": [...],
}
```

If added, existing callers that only use `status` and `warnings` must continue
to work.

### Graph and API Output

When report quality validation runs:

- graph output should continue to include `report_quality_status`;
- graph warnings should continue to include `report_quality_warning` entries
  when validation warnings exist;
- section-level citation audit details should be available in graph/API output
  either as a dedicated field or as structured warning details;
- completed runs should preserve enough detail for clients to inspect why the
  report passed or warned.

The exact persistence strategy should be chosen in the implementation slice. If
the existing result persistence can safely carry the new detail field, prefer
that. Add a migration only if tests prove a dedicated persisted column is
needed.

## Required Citation Rules

- Financial Performance must cite `[sec_company_facts]` when it includes
  source-grounded financial claims.
- Key Financial Metrics source cues should continue to cite
  `[sec_company_facts]`.
- Risk Factors should cite `[latest_10k]` when risk evidence or risk themes are
  used.
- Company Overview should cite `[latest_10k]` only when Item 1 Business
  evidence is used.
- Bull Case and Bear Case should cite source IDs when they include
  source-grounded claims.
- Sources Used should list the known source IDs used by the report.
- Missing evidence should not create fake citations.
- Unknown source IDs should produce deterministic warnings.

## Required Safety Rules

Report citation and quality checks must not:

- invent source IDs,
- infer support from a source that is not cited,
- accept unknown citation IDs as valid,
- use LLM judgment to decide whether citations are adequate,
- hide missing citation warnings inside generic prose,
- weaken existing compliance checks,
- permit financial advice language.

Warnings and limitations should remain explicit, neutral, and research-only.

## Test-Driven Workflow for 4S

Each implementation slice after 4S-0 must follow this loop:

1. Add or update tests that express the next acceptance criterion.
2. Run the targeted tests and confirm they fail for the intended reason.
3. Implement the smallest production-quality change.
4. Re-run the targeted tests and confirm they pass.
5. Run broader verification when the slice touches graph behavior, API schema,
   persistence, or documentation.

Normal tests must remain deterministic and must not call real SEC or real LLM
services.

## Acceptance Criteria

### 4S-0: Spec

- `docs/specs/4S-report-citation-audit-quality-details.md` exists.
- The spec defines problem statement, goals, non-goals, current architecture,
  input contract, output contract, citation rules, safety rules, TDD workflow,
  acceptance criteria, test plan, and definition of done.
- No validator, graph, API, persistence, report generator, or runtime behavior
  changes are made in this slice.

### 4S-1: Citation Audit Service

- Add failing tests for a deterministic citation-audit service.
- The audit extracts citations by report section.
- The audit preserves required report section order.
- The audit identifies known source IDs from `sources`.
- The audit records unknown citations.
- The audit records missing required citations by section.
- The audit handles a missing or empty report without crashing.

### 4S-2: Report Quality Detail Integration

- Add failing tests for `validate_report_quality` details.
- Existing `status` and `warnings` behavior remains compatible.
- Quality validation includes citation-audit details.
- Missing required citations include the affected section heading.
- Unknown citation warnings include the unknown source ID and affected
  sections where possible.
- Existing weak-section, missing-disclaimer, missing-SEC-source, and unsafe
  language checks continue to run.

### 4S-3: Graph and API Propagation

- Add failing graph/API tests for report quality details.
- Graph output includes section-level citation audit details when validation
  runs.
- API responses expose the details in a stable schema, or warning details carry
  the audit if a dedicated field is not added.
- Persisted completed runs preserve enough quality detail for retrieval.
- Existing clients that read only `report_quality_status` keep working.

### 4S-4: LLM Draft Citation Safety Proof

- Add failing graph tests using fake LLM report drafts.
- Drafts with missing required citations trigger deterministic fallback or
  report quality warnings.
- Drafts with unknown citations trigger deterministic warnings and do not pass
  as fully grounded reports.
- Valid LLM drafts with known citations can still be used when they pass the
  existing safety and quality gates.
- LLM call diagnostics and fallback diagnostics remain unchanged.

### 4S-5: Docs and Verification

- README documents report citation audit and quality details.
- Agent-facing docs identify Stage 4S status and remaining work.
- Focused report-validator, graph, API, and docs tests pass.
- Full verification passes:

```powershell
uv run pytest
uv run ruff check .
```

## Test Plan

### Citation Audit Tests

- Extract `[sec_company_facts]` from Financial Performance.
- Extract `[latest_10k]` from Company Overview and Risk Factors.
- Deduplicate repeated citations within a section.
- Preserve first-seen citation order.
- Mark citation-required sections when no citation exists.
- Mark unknown citations when the source ID is not present in `sources`.
- Return a stable warning audit for a missing report.
- Ignore bracketed text that does not match the source ID citation pattern.

### Report Validator Tests

- Valid reports pass with empty warnings and a passing citation audit.
- Missing citations produce section-specific warnings and audit details.
- Unknown citations produce source-specific warnings and audit details.
- Missing required sections remain reported.
- Missing research-only disclaimer remains reported.
- Scaffold language remains reported.
- Unsafe financial-advice language remains reported.
- Existing tests for warning codes remain compatible.

### Graph Tests

- Normal SEC-evidence graph runs include report quality details and pass.
- Reports generated from robust filing evidence include known citations in the
  relevant sections.
- Missing risk evidence remains a limitation without fake citations.
- Fake unsafe LLM report drafts with missing citations do not bypass quality
  validation.
- Fake LLM report drafts with unknown citations produce deterministic warnings.

### API and Persistence Tests

- Completed research retrieval includes report quality details if a dedicated
  field is added.
- Existing response fields remain compatible.
- Stored run retrieval preserves quality details or warning details.
- Run listing stays compact unless explicitly scoped otherwise.

### Documentation Tests

- README explains citation audit behavior and quality details.
- README preserves the research-only and no-financial-advice positioning.
- Agent docs identify Stage 4S status and the TDD workflow for remaining
  slices.

## Definition of Done

Stage 4S is done when:

- The 4S spec exists and matches implemented behavior.
- A deterministic citation-audit service has focused tests.
- Report quality validation exposes structured details without breaking
  existing callers.
- Graph/API results make citation audit details inspectable.
- LLM report draft citation failures are proven by graph tests.
- Missing or unknown citations become structured warnings/details.
- Valid reports continue to pass report quality validation.
- Unsafe language and scaffold-language checks remain active.
- No live SEC or live LLM calls are required in normal tests.
- README and agent docs reflect completed behavior.
- `uv run pytest` and `uv run ruff check .` pass.
