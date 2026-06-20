# Stage 4N - Report Quality and Grounding

## Problem Statement

FinSight already produces run-based, persisted research reports from SEC-derived
evidence, deterministic calculations, risk analysis, research synthesis,
optional LLM report sections, compliance checks, and report quality validation.
However, the deterministic report generator still emits scaffold and
future-work language in user-visible final reports.

Examples of current report language that is not production-quality:

- "A detailed business overview has not been generated yet"
- "This section is pending deterministic synthesis"
- "Future versions will"
- "A future LLM-assisted step"
- "This report is an MVP draft"
- "No sources were recorded"

Stage 4N makes final reports sound complete, neutral, source-grounded, and
honest about limitations without inventing missing facts or weakening the
research-only safety boundary.

## Goals

- Preserve the existing 11-section report structure.
- Preserve the required research-only disclaimer exactly.
- Remove scaffold, MVP, unfinished, and future-work language from generated
  final reports.
- Strengthen report quality validation so scaffold language is caught across
  material report sections, not only risk, bull, and bear sections.
- Make deterministic report generation professional when evidence is partial.
- Use only known structured evidence, warnings, limitations, and source
  metadata.
- Require known `source_id` citations for source-grounded claims in financial,
  risk, bull, and bear sections.
- Surface missing data as limitations or warnings instead of invented claims.
- Keep compliance checks before report quality validation in the graph.
- Preserve deterministic fallback when LLM risk analysis or report drafting is
  unavailable, invalid, unsafe, or citationless.

## Non-Goals

- Do not add investment advice, recommendations, ratings, target prices, or
  personalized guidance.
- Do not add new financial calculations outside the metrics service.
- Do not use an LLM to fill missing facts, calculate metrics, resolve
  companies, or create citations.
- Do not introduce live SEC or live LLM calls into normal unit tests.
- Do not add a frontend, export format, PDF generation, or visual report UI.
- Do not expand source collection beyond the existing SEC-derived workflow in
  this stage.
- Do not require perfect prose scoring or subjective report grading.

## Input Contract

`generate_research_report` receives structured workflow state:

- `company_name`: resolved company name, or a safe fallback from graph state.
- `ticker`: resolved ticker, or a safe fallback from graph state.
- `financial_metrics`: deterministic metrics extracted from SEC company facts,
  including period rows and metric source metadata where available.
- `latest_10k`: latest 10-K filing metadata, or `None`.
- `latest_10q`: latest 10-Q filing metadata, or `None`.
- `warnings`: structured workflow warnings that may become limitations.
- `sources`: structured source records with known `source_id` values.
- `risk_factors`: extracted risk-factor text metadata. Raw filing text must not
  be copied into the report.
- `risk_themes`: deterministic or LLM-assisted risk summaries with source IDs.
- `research_insights`: deterministic executive summary, bull case, bear case,
  and open question points.
- `llm_report_sections`: optional schema-valid, citation-validated LLM report
  sections.

`validate_report_quality` receives:

- `report`: final report text after compliance processing.
- `sources`: known structured source records used to validate citations.

## Output / Report Contract

Final reports must keep this exact section structure:

```markdown
# FinSight Research Brief: {Company Name} ({Ticker})

## 1. Research-Only Notice
## 2. Executive Summary
## 3. Company Overview
## 4. Financial Performance
## 5. Key Financial Metrics
## 6. Risk Factors
## 7. Bull Case
## 8. Bear Case
## 9. Open Questions for Further Research
## 10. Sources Used
## 11. Limitations
```

The report must include the required disclaimer exactly:

```text
This report is for informational and educational research purposes only. It is
not financial advice, investment advice, or a recommendation to buy, sell, or
hold any security.
```

When evidence exists, the report should include source-grounded, neutral prose.
When evidence is missing, the report should describe the limitation directly
without implying that the system is unfinished.

## Required Language Rules

Reports must avoid:

- Financial advice and recommendation language.
- Guaranteed or certain outcome language.
- Price predictions stated as fact.
- Scaffold, MVP, unfinished, or future-work language.
- Raw copied filing text.
- Claims unsupported by structured evidence.

Disallowed scaffold markers include at least:

- `MVP draft`
- `future versions will`
- `pending deterministic synthesis`
- `not been generated yet`
- `future LLM-assisted step`
- `no sources were recorded`
- `not generated yet`
- `has not been performed yet`

Acceptable limitation language should be user-facing and production-style, for
example:

- "Risk-factor text was not available in this run, so this report does not
  summarize filing risk themes."
- "Financial metrics were unavailable from SEC company facts for this run."
- "Source metadata was incomplete, so citations are limited to the available
  recorded source IDs."

## Required Citation and Source Rules

- Citation syntax remains `[source_id]`.
- Citations must refer to known `source_id` values when `sources` are supplied.
- Financial Performance must cite `sec_company_facts` when it discusses
  extracted metrics.
- Risk Factors must cite `latest_10k` when it discusses 10-K risk themes or
  risk-factor extraction metadata.
- Bull Case must cite known source IDs for source-grounded financial or risk
  claims.
- Bear Case must cite known source IDs for source-grounded financial or risk
  claims.
- Sources Used must list available source records with meaningful metadata such
  as SEC URL, form, filing date, accession number, report date, primary
  document, retrieval time, extracted sections, and XBRL tags where available.
- If no sources are available, the report should state this as a limitation and
  avoid source-grounded claims that require citations.

## Required Limitations Behavior

- The Limitations section must always contain professional limitation text.
- Existing workflow warnings must be represented in the Limitations section.
- If there are no warnings, include a neutral baseline limitation explaining the
  report scope, such as dependence on available SEC data and deterministic
  extraction.
- Missing metrics, missing filing text, missing risk themes, missing source
  metadata, and LLM fallback behavior must be surfaced as limitations when they
  materially affect the report.
- Limitations must not use scaffold language or apologize for unfinished
  implementation work.

## Acceptance Criteria

### 4N-0: Spec

- `docs/specs/4N-report-quality-grounding.md` exists.
- The spec defines problem statement, goals, non-goals, input contract, output
  contract, language rules, citation/source rules, limitations behavior,
  acceptance criteria, test plan, and definition of done.
- No report behavior changes are made in this slice.

### 4N-1: Validator

- Report quality validation warns on scaffold language in Company Overview,
  Risk Factors, Bull Case, Bear Case, Sources Used, and Limitations.
- Validator catches at least the disallowed scaffold markers listed in this
  spec.
- Validator continues to warn when required sections or the required disclaimer
  are missing.
- Validator continues to warn when required citation sections lack citations.
- Validator continues to warn when citations reference unknown source IDs.
- Validator does not warn on professional limitations that honestly state data
  is unavailable.

### 4N-2: Generator

- Generated reports preserve the required 11-section structure.
- Generated reports preserve the required disclaimer exactly.
- Generated reports do not contain scaffold, MVP, unfinished, or future-work
  markers.
- Company Overview uses only resolved company name, ticker, SEC source metadata,
  filing metadata, and available structured evidence.
- Financial Performance cites `sec_company_facts` when extracted metrics are
  present.
- Risk Factors cite `latest_10k` when risk themes or risk-factor extraction
  metadata are present.
- Bull Case and Bear Case preserve known source citations from research
  insights.
- Sources Used does not say "No sources were recorded"; if there are no sources,
  it uses professional limitation language.
- Limitations are present and professional even when there are no warnings.
- Raw filing text from `risk_factors[*].text` does not appear in the report.
- Generated reports avoid financial advice language.

### 4N-3: Graph Proof

- Normal graph runs produce `final_report`.
- Normal graph runs retain the required disclaimer.
- Normal graph runs with enough SEC-derived evidence end with
  `report_quality_status == "passed"`.
- Normal graph runs include known citations such as `[sec_company_facts]` and
  `[latest_10k]`.
- Normal graph runs do not add `report_quality_warning` entries caused by
  scaffold language.
- Compliance still runs before report quality validation.
- LLM fallback behavior and LLM diagnostics remain intact.

### 4N-4: Docs and Verification

- README and agent-facing docs are updated only after behavior changes are
  implemented.
- Focused tests pass for report validator, report generator, and graph behavior.
- Full verification passes:

```powershell
uv run pytest
uv run ruff check .
```

## Test Plan

### Validator Tests

- A valid production-style report passes without warnings.
- Reports containing each scaffold marker return `weak_report_section` or an
  equivalent report quality warning.
- Scaffold detection covers Company Overview, Risk Factors, Bull Case, Bear
  Case, Sources Used, and Limitations.
- Missing disclaimer returns `missing_report_disclaimer`.
- Missing required section returns `missing_report_section`.
- Citation-required sections without citations return
  `missing_section_citation`.
- Unknown citations return `unknown_report_citation`.
- Honest missing-data limitation language does not trigger scaffold warnings.

### Generator Tests

- Required sections and disclaimer are present.
- Generated report contains no scaffold markers in default or partial-data
  scenarios.
- Company Overview is professional and grounded in known company, ticker, and
  available SEC metadata.
- Metrics summary and table remain deterministic.
- Sources section lists source labels, URLs, and metadata details when present.
- Sources section uses professional limitation language when no sources exist.
- Limitations include workflow warnings.
- Limitations include baseline scope limitations when warnings are empty.
- Risk-factor raw text is not copied into the final report.
- Risk themes, bull case, and bear case preserve citations.
- LLM report sections are still preferred only after graph validation has
  accepted them.

### Graph Tests

- Successful graph run produces a final report with required disclaimer,
  citations, passing quality status, and no scaffold quality warnings.
- Existing deterministic LLM fallback tests continue to pass.
- Citationless LLM report draft still falls back to deterministic generation.
- Compliance rewrite still occurs before quality validation.
- Compliance blocked path still stops before validation.

## Definition of Done

Stage 4N is done when:

- The 4N spec exists and matches implemented behavior.
- Validator tests are written before validator changes and pass after
  implementation.
- Generator tests are written before generator changes and pass after
  implementation.
- Graph proof tests pass and confirm production-style, source-grounded reports.
- Final reports keep the required 11 sections and disclaimer.
- Final reports avoid scaffold/MVP/future-work language.
- Final reports use known source ID citations for grounded claims.
- Missing data appears as limitations or warnings, not invented facts.
- Compliance and report quality validation preserve the current graph order.
- `uv run pytest` and `uv run ruff check .` pass.
