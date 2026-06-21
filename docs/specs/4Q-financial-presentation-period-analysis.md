# Stage 4Q - Financial Presentation and Period Analysis

## Problem Statement

FinSight now produces production-style, source-grounded research reports with
SEC filing evidence, deterministic business overview support, optional
provider-backed LLM drafting, compliance checks, and report quality validation.
The financial calculations are deterministic, but the user-facing financial
presentation is still too raw for a research brief.

Current report output can expose unformatted values such as `1250000000` and
`280000000`. It also presents period rows without a concise explanation of what
changed between periods. This makes reports technically correct but harder to
read, scan, and test as a professional equity research artifact.

Stage 4Q improves financial presentation and period analysis while preserving
the existing safety boundary: SEC company facts remain the source of truth,
financial calculations remain Python-based and deterministic, and the LLM must
not create, calculate, or repair financial facts.

## Goals

- Format monetary values in report prose and tables using readable units such
  as `$1.25B`, `$280.0M`, `$950.0K`, and `N/A`.
- Format percentages consistently in report prose and tables.
- Preserve raw numeric values in internal metric objects for calculations and
  tests.
- Add deterministic period comparison output derived only from extracted metric
  periods.
- Explain revenue growth, margin movement, free cash flow changes, and selected
  balance-sheet changes when enough period data exists.
- Surface missing prior-period data as limitations or careful language instead
  of inventing comparisons.
- Improve the Key Financial Metrics table with readable values, units, periods,
  and source cues.
- Preserve known `source_id` citations, especially `[sec_company_facts]`, for
  financial claims.
- Preserve the required 11-section report structure and required disclaimer.
- Keep normal tests deterministic with fixtures and fake graph dependencies.

## Non-Goals

- Do not add new financial metrics beyond the existing deterministic metrics
  unless a later stage explicitly scopes them.
- Do not change SEC company facts retrieval or filing selection behavior.
- Do not use an LLM for calculations, value formatting, period comparisons, or
  filling missing values.
- Do not add valuation models, ratios that imply recommendations, target
  prices, ratings, or buy/sell/hold language.
- Do not add market price data, analyst estimates, peer benchmarking, or
  external fundamentals providers.
- Do not require exact live SEC or live LLM behavior in normal tests.
- Do not change persistence schemas unless a later implementation slice proves
  it is necessary.
- Do not build a frontend, charting UI, PDF export, or spreadsheet export in
  this stage.

## Current Financial Architecture

The existing implementation includes:

- `extract_financial_metrics(company_facts)` in
  `src/finsight_agent/app/services/metrics.py`.
- Deterministic extraction of revenue, net income, operating income, assets,
  liabilities, cash, debt, operating cash flow, capital expenditure, free cash
  flow, margins, and revenue growth.
- Per-period `metric_sources` metadata with XBRL tag, unit, form, filing date,
  period, and accession details where available.
- Report generation in
  `src/finsight_agent/app/services/report_generator.py`.
- Existing sections:
  - `## 4. Financial Performance`
  - `## 5. Key Financial Metrics`
- Existing source ID for company facts: `sec_company_facts`.

Stage 4Q should improve presentation and analysis around these existing
objects rather than replacing the metrics layer.

## Input Contract

### Metrics Input

Report generation receives `financial_metrics` with a `periods` list. Periods
may include:

```python
{
    "fy": 2024,
    "revenue": 1250000000,
    "revenue_growth": 0.25,
    "operating_income": 300000000,
    "operating_margin": 0.24,
    "net_income": 250000000,
    "net_margin": 0.2,
    "assets": 4000000000,
    "liabilities": 2400000000,
    "cash": 900000000,
    "debt": 850000000,
    "operating_cash_flow": 400000000,
    "capital_expenditure": 120000000,
    "free_cash_flow": 280000000,
    "metric_sources": {...},
}
```

Rules:

- Raw values stay numeric in the metrics service output.
- Calculated ratios stay decimal numbers, for example `0.25` for `25.0%`.
- Missing values stay `None`.
- Period ordering should be deterministic by fiscal year.
- Report formatting must not mutate the input metrics object.

### Source Input

Financial report sections may receive source records that include:

- `source_id="sec_company_facts"`
- SEC company facts URL
- `metric_fiscal_years`
- `xbrl_tags_used`
- retrieval timestamp
- per-period `metric_sources`

The report may use these fields for readable source cues, table footnotes, or
limitations, but must not invent missing source metadata.

### LLM Draft Input

If `llm_report_sections["financial_performance"]` is present and has already
passed graph validation, the report may use it. Stage 4Q must not let LLM text
replace deterministic metric tables or deterministic source metadata.

The LLM must not be asked to calculate or format financial values in this
stage.

## Output Contract

### Financial Performance Section

When metrics are available, Financial Performance should include:

- latest fiscal year,
- readable revenue,
- readable net income when available,
- readable free cash flow when available,
- readable revenue growth when available,
- at least one deterministic period comparison when enough data exists,
- citation to `[sec_company_facts]`.

Example style:

```text
For fiscal year 2024, extracted revenue was $1.25B, net income was $250.0M, and
free cash flow was $280.0M. Revenue increased 25.0% from fiscal year 2023 to
2024. [sec_company_facts]
```

When metrics are unavailable, the section should keep professional limitation
language and cite `[sec_company_facts]` only if that source record exists or the
workflow uses it as the known company-facts evidence source.

### Key Financial Metrics Section

The metrics table should:

- use readable monetary values,
- use readable percentages,
- show `N/A` for missing values,
- preserve deterministic fiscal-year ordering,
- include the existing major rows or columns that users already expect,
- include source cues or a short note that values come from SEC company facts,
- avoid raw large integers in final report output.

Table shape may evolve, but it should remain easy to scan in Markdown and
stable enough for tests.

### Period Analysis Output

Period analysis should be deterministic and derived only from period data.
Potential output includes:

- revenue increased, decreased, or was flat year over year,
- operating margin expanded, contracted, or was unavailable,
- net margin expanded, contracted, or was unavailable,
- free cash flow increased, decreased, turned positive, turned negative, or was
  unavailable,
- cash, debt, assets, and liabilities changed when both comparable values
  exist.

The analysis should prefer concise, factual language. It must not imply a
forecast, recommendation, or certainty about future performance.

### Limitations Output

Limitations should mention materially missing financial context when relevant,
including:

- no extractable revenue,
- only one period available,
- missing net income,
- missing operating income,
- missing cash flow or capital expenditure,
- missing source metadata for extracted values.

Existing warnings from the metrics service may continue to flow into the
Limitations section.

## Formatting Rules

### Monetary Values

- `None` renders as `N/A`.
- Positive USD values render with `$`.
- Negative USD values render with a leading minus sign before `$`, for example
  `-$45.0M`.
- Absolute values greater than or equal to one trillion render as trillions,
  for example `$1.20T`.
- Absolute values greater than or equal to one billion render as billions, for
  example `$1.25B`.
- Absolute values greater than or equal to one million render as millions, for
  example `$280.0M`.
- Absolute values greater than or equal to one thousand render as thousands,
  for example `$950.0K`.
- Smaller values render as whole dollars when they are whole numbers.
- Formatting must be deterministic and locale-independent.

### Percentage Values

- `None` renders as `N/A`.
- Percentages render from decimal inputs, for example `0.25` becomes `25.0%`.
- Negative percentages preserve the sign, for example `-0.035` becomes
  `-3.5%`.
- Use one decimal place for report prose and tables unless tests specify a
  more precise internal value.
- Avoid implying precision that is not meaningful for a research brief.

### Missing Data

- Missing metrics render as `N/A` in tables.
- Missing comparison baselines should produce no comparison claim or a careful
  limitation.
- Missing source metadata should not block report generation, but should be
  visible through source details or limitations when material.

## Period Comparison Rules

- Compare fiscal years only when both current and previous values are numeric.
- Use the latest period and immediate prior period for headline comparisons.
- If more than two periods are available, preserve all table rows and use the
  latest pair for concise summary prose.
- Revenue growth can use the existing `revenue_growth` field when present.
- If `revenue_growth` is missing but current and prior revenue exist, a
  deterministic helper may calculate the same value for presentation only.
- Margin movement should compare current and prior margin values in percentage
  points.
- Free cash flow change should compare current and prior free cash flow values
  when both exist.
- Avoid division by zero; if the prior value is zero, state that percentage
  growth is not meaningful or omit the percentage claim.
- Do not annualize interim data in this stage.

## Required Source and Citation Rules

- Financial Performance claims based on extracted company facts must cite
  `[sec_company_facts]`.
- Key Financial Metrics should include a source cue for SEC company facts.
- Citations must refer to known source IDs when source records are supplied.
- Per-metric source details may include XBRL tags, forms, filing dates, periods,
  and accession numbers where available.
- Unknown citations remain invalid under the report quality validator.
- Missing company facts must not create fake citations or invented values.

## Required Language Rules

Financial sections must avoid:

- financial advice,
- buy/sell/hold recommendations,
- target prices,
- price predictions stated as fact,
- guaranteed future outcomes,
- unsupported trend claims,
- raw copied filing text,
- scaffold language.

Acceptable language examples:

- "Revenue increased 25.0% from fiscal year 2023 to 2024."
- "Operating margin was unavailable because operating income was not extracted
  for the comparable period."
- "Only one fiscal year was available, so year-over-year comparisons are
  limited."
- "Free cash flow is calculated as operating cash flow less capital
  expenditure using extracted SEC company facts."

## Test-Driven Workflow for 4Q

Each implementation slice after 4Q-0 must follow this loop:

1. Add or update tests that express the next acceptance criterion.
2. Run the targeted tests and confirm they fail for the intended reason.
3. Implement the smallest production-quality change.
4. Re-run the targeted tests and confirm they pass.
5. Run broader verification when the slice touches graph behavior or report
   quality behavior.

Normal tests must remain deterministic and must not call real SEC or real LLM
services.

## Acceptance Criteria

### 4Q-0: Spec

- `docs/specs/4Q-financial-presentation-period-analysis.md` exists.
- The spec defines problem statement, goals, non-goals, input contract, output
  contract, formatting rules, period comparison rules, source/citation rules,
  language rules, TDD workflow, acceptance criteria, test plan, and definition
  of done.
- No metrics, graph, report generator, validator, API, or docs behavior changes
  are made in this slice.

### 4Q-1: Financial Formatting Helpers

- Add failing tests for monetary and percentage formatting.
- Monetary values render as `$1.25B`, `$280.0M`, `$950.0K`, whole dollars, and
  `N/A` according to this spec.
- Negative monetary values render with a clear sign.
- Percentages render as `25.0%`, `-3.5%`, and `N/A`.
- Formatting helpers are deterministic, unit-testable, and do not mutate metric
  inputs.
- Existing report generator tests are updated only where raw-value assertions
  intentionally change to formatted-value assertions.

### 4Q-2: Deterministic Period Comparison

- Add failing tests for latest-period comparisons.
- Period analysis identifies revenue increases, decreases, flat revenue, and
  unavailable comparisons.
- Period analysis identifies margin expansion or contraction in percentage
  points when comparable margins exist.
- Period analysis identifies free cash flow changes when comparable values
  exist.
- One-period datasets produce careful limitation language rather than invented
  trends.
- Prior-zero comparisons avoid invalid percentage growth.

### 4Q-3: Report Financial Section Integration

- Add failing report generator tests before implementation.
- Financial Performance uses formatted monetary and percentage values.
- Financial Performance includes concise deterministic period analysis when
  enough data exists.
- Key Financial Metrics table uses formatted values and percentages.
- Key Financial Metrics includes a source cue for `[sec_company_facts]`.
- Raw large integers such as `1250000000` and `280000000` no longer appear in
  the final report financial sections.
- Missing values render as `N/A` and are reflected in limitations where
  material.
- The report still passes quality validation with full evidence.

### 4Q-4: Graph Proof and Quality Guardrails

- Add graph-level tests before implementation if graph behavior changes.
- A normal graph run with fixture SEC evidence produces formatted financial
  values in the final report.
- The graph result still has `report_quality_status == "passed"` when enough
  SEC-derived evidence exists.
- Final reports still include the required disclaimer and required 11 sections.
- Final reports still cite `[sec_company_facts]` for financial claims.
- LLM report drafting cannot bypass deterministic metric table formatting.
- Existing LLM fallback and diagnostics behavior remains intact.

### 4Q-5: Docs and Verification

- README and agent-facing docs document the improved financial presentation
  after behavior changes are implemented.
- Documentation explains that financial calculations are deterministic and
  source-grounded.
- Documentation explains that raw metric values remain internal while reports
  use readable presentation values.
- Focused tests for metrics presentation, report generation, and graph proof
  pass.
- Full verification passes:

```powershell
uv run pytest
uv run ruff check .
```

## Test Plan

### Formatting Tests

- Format `1250000000` as `$1.25B`.
- Format `280000000` as `$280.0M`.
- Format `950000` as `$950.0K`.
- Format `999` as `$999`.
- Format `-45000000` as `-$45.0M`.
- Format `None` as `N/A`.
- Format `0.25` as `25.0%`.
- Format `-0.035` as `-3.5%`.
- Format `None` as `N/A`.

### Period Analysis Tests

- Latest revenue increase produces a year-over-year increase sentence.
- Latest revenue decrease produces a year-over-year decrease sentence.
- Flat revenue produces a neutral flat-revenue sentence.
- Missing prior period produces a one-period limitation.
- Prior revenue of zero avoids percentage-growth output.
- Operating margin movement is expressed in percentage points.
- Net margin movement is expressed in percentage points.
- Free cash flow increase and decrease are expressed with formatted values.
- Missing free cash flow produces no invented free-cash-flow comparison.

### Report Generator Tests

- Financial Performance summary uses formatted values.
- Financial Performance includes latest fiscal year and comparison language.
- Financial Performance cites `[sec_company_facts]`.
- Key Financial Metrics table uses formatted monetary values.
- Key Financial Metrics table uses one-decimal percentages.
- Key Financial Metrics table shows `N/A` for missing values.
- Report financial sections do not contain raw large integers.
- Full-evidence report still passes report quality validation.
- LLM financial prose, when accepted by the graph, does not remove the
  deterministic metrics table.

### Graph Tests

- Fixture graph run produces formatted financial values in `final_report`.
- Fixture graph run includes `[sec_company_facts]` in financial sections.
- Fixture graph run passes report quality validation.
- Citationless or unsafe LLM drafting fallback behavior remains unchanged.

### Documentation Tests

- README documents readable financial presentation.
- README preserves the research-only and no-financial-advice positioning.
- Agent docs identify Stage 4Q status and the TDD workflow for remaining
  slices.

## Definition of Done

Stage 4Q is done when:

- The 4Q spec exists and matches implemented behavior.
- Formatting helper tests are written before helper implementation and pass
  after implementation.
- Period analysis tests are written before period analysis implementation and
  pass after implementation.
- Report generator tests are written before report changes and pass after
  implementation.
- Graph proof confirms formatted financial presentation in final reports.
- Financial calculations remain deterministic Python calculations.
- Raw metric values remain available internally for calculations and tests.
- Final report financial sections use readable values, careful comparisons,
  known citations, and professional limitations.
- Missing data appears as `N/A`, warnings, or limitations, not invented facts.
- LLM usage remains limited to allowed drafting and summarization tasks.
- Normal tests do not require real SEC or real LLM calls.
- README and agent docs reflect completed behavior.
- `uv run pytest` and `uv run ruff check .` pass.
