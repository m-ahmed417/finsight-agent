# Stage 4T - Evaluation Harness and Regression Suites

## Problem Statement

FinSight now has a source-grounded backend workflow with deterministic SEC
retrieval fixtures, filing extraction robustness, readable financial
presentation, citation audit details, LLM provider guardrails, compliance
checks, persistence, and API retrieval.

The next reliability bottleneck is regression evaluation across realistic
research scenarios. Unit tests and graph tests prove narrow behaviors, but they
do not yet provide a single repeatable view of whether the agent still produces
safe, grounded, useful research briefs across multiple end-to-end cases.

Stage 4T adds an evaluation harness and deterministic regression suites. The
goal is not to replace unit tests or introduce subjective model judging. The
goal is to define repeatable eval cases, run them with fake SEC and fake LLM
dependencies by default, score objective quality checks, and produce readable
results that can be used locally and in CI.

## Goals

- Add a deterministic eval harness for graph-level research scenarios.
- Define eval case inputs, fake dependencies, expected warnings, and objective
  pass criteria in structured data.
- Evaluate final report structure, research-only disclaimer, compliance status,
  report quality status, citation audit details, known source IDs, forbidden
  language, and fallback behavior.
- Cover normal, degraded, and adversarial cases such as missing filing sections,
  noisy filings, unsafe LLM report drafts, missing citations, and unknown
  citations.
- Produce concise eval result summaries for local use and CI logs.
- Keep normal evals fixture-backed, deterministic, and free of live SEC/LLM
  calls.
- Preserve existing unit, graph, API, repository, migration, and live smoke
  tests.
- Make future optional live evals explicit and opt-in.

## Non-Goals

- Do not use an LLM-as-judge in default evals.
- Do not call live SEC or live model APIs in normal eval runs.
- Do not create investment recommendations, ratings, target prices, forecasts,
  or portfolio guidance.
- Do not add market price data, analyst estimates, peer benchmarking, or
  external fundamentals providers.
- Do not replace existing pytest unit or graph tests.
- Do not require a frontend, dashboard, PDF export, or notebook in this stage.
- Do not make exact prose snapshots the primary quality signal.
- Do not use eval failures to auto-rewrite reports.
- Do not introduce another persistence table unless a later slice proves it is
  necessary.

## Current Evaluation Architecture

The project already has strong deterministic test surfaces:

- Parser tests in `tests/test_filing_parser.py`.
- Report generator tests in `tests/test_report_generator.py`.
- Report validator and citation audit tests in:
  - `tests/test_report_validator.py`
  - `tests/test_report_citation_audit.py`
- Graph tests with fake SEC and fake LLM clients in `tests/test_graph.py`.
- API/repository/migration tests for persisted research runs.
- Live smoke tests that are skipped by default and gated behind environment
  variables such as `RUN_LIVE_LLM_TESTS`, `RUN_LIVE_SEC_GRAPH_TESTS`, and
  `RUN_LIVE_SEC_LLM_GRAPH_TESTS`.

Stage 4T should build an eval layer on top of these capabilities rather than
duplicating all unit tests.

## Input Contract

### Eval Case Input

Each deterministic eval case should describe:

```python
{
    "id": "normal_aapl_sec_fixture",
    "query": "AAPL",
    "description": "Normal fixture-backed SEC run.",
    "sec_fixture": "sample_10k_excerpt",
    "llm_fixture": "mock_valid_report_draft",
    "expected": {
        "status": "completed",
        "report_quality_status": "passed",
        "compliance_status": "allowed",
        "required_citations": ["sec_company_facts", "latest_10k"],
        "forbidden_phrases": ["you should buy", "guaranteed"],
        "required_warning_codes": [],
        "forbidden_warning_codes": ["report_quality_warning"],
    },
}
```

The exact Python representation can be refined during implementation. It may be
a dataclass, Pydantic model, or plain typed dictionary, but it must be
deterministic and easy to extend.

### Eval Runner Input

The runner should accept:

- a suite name,
- a list of eval cases,
- a graph factory or graph runner,
- fake SEC clients and fake LLM clients selected by each case,
- optional output format settings.

Normal evals should use local fixtures and fake clients only.

## Output Contract

### Eval Case Result

Each eval case should produce structured output such as:

```python
{
    "case_id": "normal_aapl_sec_fixture",
    "status": "passed" | "failed",
    "checks": [
        {
            "name": "report_quality_status",
            "status": "passed",
            "expected": "passed",
            "actual": "passed",
        }
    ],
    "metrics": {
        "required_sections_present": True,
        "citation_validity": True,
        "compliance_passed": True,
        "fallback_behavior_correct": True,
    },
    "warnings": [],
}
```

### Eval Suite Result

The suite should produce deterministic summary output such as:

```python
{
    "suite": "deterministic_graph_quality",
    "case_count": 8,
    "passed": 8,
    "failed": 0,
    "pass_rate": 1.0,
    "cases": [...],
}
```

The initial output can be returned as Python objects and printed by a command.
JSON or Markdown export may be added if useful during implementation.

## Required Eval Dimensions

Deterministic evals should check:

- required 11-section report structure,
- research-only disclaimer,
- absence of financial advice language,
- absence of scaffold language,
- `compliance_status`,
- `report_quality_status`,
- `report_quality_details.citation_audit.status`,
- known source IDs in `citation_audit.known_source_ids`,
- `unknown_citations` is empty for passing cases,
- `sections_missing_required_citations` is empty for passing cases,
- expected warning codes for degraded cases,
- expected fallback warnings for unsafe or invalid LLM drafts,
- absence of raw filing text in final reports,
- absence of raw financial metric values in final report prose,
- source IDs in report text only cite known sources.

## Required Eval Cases

The first deterministic suite should include cases such as:

- normal AAPL fixture run,
- latest 10-K with heading variants,
- latest 10-K with table-of-contents noise,
- missing Item 1 Business section,
- missing Item 1A Risk Factors section,
- filing document unavailable,
- LLM report draft with missing required citations,
- LLM report draft with unknown citations,
- LLM report draft with unsafe financial-advice language,
- limited financial data or one-period metrics.

The exact first suite can start smaller, but it should include at least normal,
degraded filing, and adversarial LLM cases by the end of Stage 4T.

## Required Safety Rules

Evals must not:

- rely on live services by default,
- use an LLM judge by default,
- assert exact full report prose unless the text is intentionally stable,
- accept reports with unknown citations as fully passing,
- accept reports with buy/sell/hold language,
- accept fake citations created to hide missing evidence,
- hide limitations when expected evidence is unavailable.

When a case is degraded by design, the eval should assert clear warnings or
limitations instead of expecting invented completeness.

## Optional Live Eval Rules

Live evals may be added later, but they must be opt-in. Suggested flags:

```powershell
$env:RUN_LIVE_SEC_EVALS="1"
$env:RUN_LIVE_LLM_EVALS="1"
$env:RUN_LIVE_SEC_LLM_EVALS="1"
```

Live evals should avoid exact prose assertions. They should evaluate structure,
safety, citations, statuses, warnings, and stable metadata instead.

## Test-Driven Workflow for 4T

Each implementation slice after 4T-0 must follow this loop:

1. Add or update tests for the next eval acceptance criterion.
2. Run the targeted tests and confirm they fail for the intended reason.
3. Implement the smallest production-quality change.
4. Re-run the targeted tests and confirm they pass.
5. Run broader verification when the slice touches graph behavior, commands,
   docs, API schema, or persistence.

Normal tests and normal evals must remain deterministic and must not call real
SEC or real LLM services.

## Acceptance Criteria

### 4T-0: Spec

- `docs/specs/4T-evaluation-harness-regression-suites.md` exists.
- The spec defines problem statement, goals, non-goals, current architecture,
  input contract, output contract, eval dimensions, required cases, safety
  rules, optional live eval rules, TDD workflow, acceptance criteria, test
  plan, and definition of done.
- No eval runner, graph, API, persistence, README, or runtime behavior changes
  are made in this slice.

### 4T-1: Eval Case and Result Models

- Add failing tests for eval case/result models.
- Define deterministic eval case representation.
- Define per-check result representation.
- Define suite summary representation.
- Validate required fields and reject malformed cases.
- Keep models independent from live services.

### 4T-2: Deterministic Report Evaluators

- Add failing tests for reusable evaluator functions.
- Evaluate required report sections.
- Evaluate research-only disclaimer presence.
- Evaluate forbidden financial-advice and scaffold language.
- Evaluate required and unknown citations from `report_quality_details`.
- Evaluate warning codes and fallback warning codes.
- Return structured check results without raising for expected failures.

### 4T-3: Graph Eval Suite

- Add failing tests for a deterministic graph eval suite.
- Use fake SEC clients and fake LLM clients.
- Include normal, degraded filing, and adversarial LLM cases.
- Produce passing suite results when current graph behavior meets expectations.
- Include useful failure messages when a check fails.

### 4T-4: Eval Runner Command and CI-Friendly Output

- Add failing tests for a command or module entry point.
- Provide a local command such as:

```powershell
uv run python -m finsight_agent.evals.run
```

- Print deterministic suite summaries.
- Exit with non-zero status when eval cases fail.
- Avoid live SEC/LLM calls unless explicit live flags are set.
- Keep output concise enough for CI logs.

### 4T-5: Docs and Verification

- README documents deterministic evals and how to run them.
- Agent-facing docs identify Stage 4T status and remaining work.
- Focused eval, graph, report-quality, and docs tests pass.
- Full verification passes:

```powershell
uv run pytest
uv run ruff check .
```

## Test Plan

### Eval Model Tests

- Valid eval cases parse successfully.
- Missing required fields are rejected.
- Result models compute passed/failed counts and pass rate.
- Case IDs are stable and non-empty.
- Expected warning/citation fields default safely.

### Evaluator Tests

- Reports with all required sections pass section checks.
- Missing required sections fail with section names.
- Reports missing the disclaimer fail.
- Reports with forbidden advice language fail.
- Reports with scaffold language fail.
- Citation audit with unknown citations fails the citation check.
- Citation audit with missing required citations fails the citation check.
- Expected warning codes pass when present and fail when missing.
- Forbidden warning codes fail when present.

### Graph Eval Tests

- Normal fixture-backed run passes the deterministic graph eval.
- Heading variant fixture run passes.
- Table-of-contents fixture run passes.
- Missing business section case passes only when the expected warning and
  limitation are present.
- Missing risk section case passes only when the expected warning and limitation
  are present.
- Citationless LLM report draft case passes only when deterministic fallback is
  used.
- Unknown-citation LLM report draft case passes only when deterministic fallback
  is used.
- Unsafe LLM report draft case passes only when compliance rewrite or fallback
  behavior is correct.

### Command Tests

- Eval command returns zero when all deterministic cases pass.
- Eval command returns non-zero when a case fails.
- Eval command prints suite name, case count, pass count, fail count, and failed
  case IDs.
- Eval command does not require live environment variables.

### Documentation Tests

- README documents deterministic evals.
- README documents optional live eval flags if live evals are added.
- Agent docs identify Stage 4T status and slice history.

## Definition of Done

Stage 4T is done when:

- The 4T spec exists and matches implemented behavior.
- Deterministic eval case/result models are tested.
- Reusable report/citation/compliance evaluators are tested.
- A graph-level deterministic eval suite covers normal, degraded, and
  adversarial cases.
- A local eval command or module entry point runs the deterministic suite.
- Eval output is concise, structured, and CI-friendly.
- Default evals do not call live SEC or LLM services.
- Optional live evals, if added, are explicitly gated.
- README and agent docs reflect completed behavior.
- `uv run pytest` and `uv run ruff check .` pass.
