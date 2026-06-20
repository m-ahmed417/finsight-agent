# Stage 4P - LLM Provider Integration and Agent Testing

## Problem Statement

FinSight now has a source-grounded deterministic research workflow. Stages 4N
and 4O made final reports production-style, citation-aware, grounded in SEC
evidence, and honest about limitations. The LLM path exists, but it still needs
a tighter provider integration and testing plan before routine agent testing
with real model APIs.

The system should allow controlled use of real LLM providers for risk
summarization and report section drafting while preserving deterministic SEC
data retrieval, Python-based financial calculations, citation validation,
compliance checks, report quality validation, and persisted LLM diagnostics.

Stage 4P introduces the model API testing discipline around the existing LLM
adapter. The goal is not to make the LLM the source of truth. The goal is to
make provider usage safe, observable, opt-in, and testable.

## Goals

- Harden LLM provider configuration for `mock`, `openai`, and `deepseek`.
- Keep `mock` as the deterministic default for local development, tests, and CI.
- Make missing or invalid provider credentials fail clearly before workflow
  execution.
- Define evidence contracts for LLM risk analysis and report drafting.
- Ensure LLM prompts require source-grounded, citation-aware, research-only
  output.
- Preserve deterministic fallback when provider calls fail, return invalid
  JSON, omit citations, include unsafe language, or otherwise violate schema.
- Record provider, model, prompt version, timing, token usage, request IDs,
  fallback status, and error details where available.
- Add opt-in live smoke tests for real provider calls.
- Add a controlled end-to-end agent testing workflow that can be run manually
  against real SEC data and a real model provider.
- Update README and agent docs so model API testing is clear and safe.

## Non-Goals

- Do not make live LLM calls in normal unit tests or default CI.
- Do not use LLMs for company resolution, financial calculations, source
  creation, citation creation, or filling missing facts.
- Do not let LLM output bypass deterministic compliance and report quality
  validation.
- Do not add recommendations, ratings, target prices, investment advice, or
  personalized guidance.
- Do not introduce new model providers beyond `mock`, `openai`, and `deepseek`
  in this stage.
- Do not build a frontend or chat UI in this stage.
- Do not require exact LLM prose snapshots in tests.
- Do not store API keys or secrets in committed files.

## Current LLM Architecture

The existing implementation includes:

- `MockLLMClient` for deterministic local behavior.
- `ChatModelLLMClient` for LangChain-backed providers.
- `get_llm_client(settings)` provider selection.
- `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`, and `DEEPSEEK_API_KEY`
  settings.
- LLM-aware graph nodes:
  - `analyze_risks`
  - `draft_report`
- Prompt versions:
  - `risk_analysis:v1`
  - `report_drafting:v1`
- LLM call events persisted in research runs.
- LLM usage summary endpoint.
- Opt-in `tests/test_live_llm.py` smoke test.

Stage 4P should strengthen, document, and prove this path rather than replacing
the deterministic workflow.

## Input Contract

### Provider Configuration Input

LLM provider configuration comes from environment-backed settings:

```text
LLM_PROVIDER=mock | openai | deepseek
LLM_MODEL=<provider model name>
OPENAI_API_KEY=<required when LLM_PROVIDER=openai>
DEEPSEEK_API_KEY=<required when LLM_PROVIDER=deepseek>
```

Rules:

- `LLM_PROVIDER=mock` must not require API keys.
- Real providers must require their matching API key.
- Unsupported providers must fail with a clear configuration error.
- Empty model names for real providers must fail with a clear configuration
  error.
- Provider and model values should be normalized for comparison but preserved
  in diagnostics where useful.

### Risk Analysis Evidence Input

Risk analysis LLM calls may receive:

- extracted risk-factor records,
- source IDs,
- filing metadata,
- source URLs,
- truncated risk text when needed,
- prompt version,
- required output schema.

The LLM may summarize and classify risk themes. It must not create new sources
or claims outside supplied evidence.

### Report Drafting Evidence Input

Report drafting LLM calls may receive structured evidence only:

- resolved company identity,
- latest filing metadata,
- deterministic financial metrics and metric source metadata,
- extracted risk themes,
- deterministic research insights,
- deterministic business overview evidence,
- known source records,
- workflow warnings and limitations.

The report drafting prompt must tell the model:

- use only supplied evidence,
- preserve known `source_id` citations,
- do not invent citations,
- do not provide financial advice,
- do not make price predictions as fact,
- return only valid JSON matching the required schema.

## Output Contract

### Risk Analysis Output

LLM risk analysis must produce schema-valid structured themes:

```json
{
  "themes": [
    {
      "title": "string",
      "summary": "string"
    }
  ],
  "warnings": ["optional string warnings"]
}
```

The application normalizes risk themes by adding deterministic source metadata
from the input risk-factor records.

If output is invalid, empty, unsafe, or unavailable, the workflow must fall back
to deterministic risk analysis and record a warning.

### Report Drafting Output

LLM report drafting must produce schema-valid report sections:

```json
{
  "executive_summary": ["string"],
  "financial_performance": "string",
  "risk_factors": ["string"],
  "bull_case": ["string"],
  "bear_case": ["string"],
  "open_questions": ["string"],
  "warnings": ["optional string warnings"]
}
```

The graph must validate that source-grounded drafted sections cite known source
IDs before using the LLM draft. Invalid or citationless drafts must fall back to
deterministic report generation.

### Diagnostics Output

LLM-aware workflow steps and persisted call events should preserve:

- provider,
- model,
- task,
- prompt version,
- start and completion timestamps,
- duration,
- status: `completed`, `failed`, or `skipped`,
- whether fallback was used,
- fallback reason when applicable,
- token usage when available,
- provider request ID when available,
- error type and message when available.

## Required Safety Rules

- LLM output is advisory drafting only; SEC evidence and deterministic services
  remain source of truth.
- Financial calculations remain deterministic Python calculations.
- The LLM must not resolve companies or select filings.
- The LLM must not invent products, segments, financial values, filing dates,
  citations, risks, or sources.
- All final reports still pass through compliance checks.
- All final reports still pass through report quality validation.
- Unknown citations must cause fallback or report quality warnings.
- Unsafe LLM report language must be rewritten or blocked by compliance.
- Missing provider credentials must fail before live calls are attempted.
- Normal tests must not require network access.

## Prompt and Evidence Rules

- Include prompt versions in every provider call.
- Keep prompts explicit about research-only behavior.
- Include the required output schema in the user payload.
- Send structured JSON evidence instead of free-form prompt stuffing.
- Prefer compact structured summaries and metadata over large raw text.
- Truncate oversized risk-factor text with a structured warning.
- Do not send secrets, database URLs, local file paths, or environment details
  to model providers.
- Preserve source IDs exactly as known by the workflow.

## Agent Testing Workflow

Controlled agent testing should have three levels:

1. Deterministic local run:
   - `LLM_PROVIDER=mock`
   - normal unit tests
   - no network model calls

2. Provider smoke test:
   - opt-in environment flag
   - real provider credentials
   - small fixture-like prompt
   - verifies schema shape, diagnostics, and fallback behavior where feasible

3. End-to-end live agent smoke test:
   - opt-in environment flag
   - real SEC data
   - real model provider
   - mock remains unavailable only by deliberate configuration
   - verifies final report, citations, compliance status, report quality status,
     LLM call events, and usage summary

The live end-to-end smoke test should avoid exact prose assertions. It should
assert structure, safety, citations, source IDs, diagnostics, and terminal run
status.

## Acceptance Criteria

### 4P-0: Spec

- `docs/specs/4P-llm-provider-integration-agent-testing.md` exists.
- The spec defines problem statement, goals, non-goals, input contract, output
  contract, safety rules, prompt/evidence rules, diagnostics, agent testing
  workflow, acceptance criteria, test plan, and definition of done.
- No LLM client, graph, API, docs, or test behavior changes are made in this
  slice.

### 4P-1: Provider Configuration Hardening

- Add failing tests for provider configuration edge cases.
- `LLM_PROVIDER=mock` remains default and requires no API key.
- `openai` and `deepseek` require non-empty provider-specific API keys.
- Real providers require a non-empty `LLM_MODEL`.
- Unsupported providers fail with clear messages.
- Provider selection remains deterministic and unit-testable without network
  calls by monkeypatching model initialization.

### 4P-2: Prompt and Evidence Contract Hardening

- Add failing tests for the JSON payloads sent to risk and report prompts.
- Risk prompts include prompt version, required schema, source IDs, and filing
  metadata.
- Report prompts include prompt version, required schema, known sources,
  business overview evidence, research insights, financial metrics, risks, and
  warnings.
- Report drafting prompt explicitly forbids unsupported facts, invented
  citations, financial advice, and price predictions.
- Oversized risk text is truncated with a structured warning.
- Secrets and local environment details are not included in prompt payloads.

### 4P-3: LLM Output Validation and Fallback Proof

- Add or strengthen tests proving invalid JSON, invalid schemas, blank fields,
  empty themes, citationless drafts, and unsafe drafts do not bypass fallback,
  compliance, or quality validation.
- LLM warnings are preserved as structured workflow warnings.
- Known source citations are validated before LLM report sections are used.
- Deterministic fallback still produces a safe final report when enough SEC
  evidence exists.

### 4P-4: Live Provider Smoke Tests and Documentation

- Add opt-in live LLM smoke coverage for provider-backed risk analysis and
  report drafting.
- Live tests are skipped unless an explicit environment variable is set.
- Live tests do not run in normal CI.
- README documents how to configure `mock`, `openai`, and `deepseek`.
- README documents how to run live provider smoke tests safely.
- Agent docs identify 4P status and the controlled testing workflow.

### 4P-5: End-to-End Agent Testing Workflow

- Add an opt-in live SEC plus live LLM graph smoke test or documented command
  path that exercises the agent end to end.
- The live agent test verifies:
  - run completes or fails with structured errors,
  - final report contains the required disclaimer when completed,
  - known citations are present,
  - compliance status is recorded,
  - report quality status is recorded,
  - LLM call events are persisted,
  - LLM usage summary is available,
  - deterministic fallback is visible when used.
- Exact model prose is not asserted.
- Full default verification still passes without live flags:

```powershell
uv run pytest
uv run ruff check .
```

## Test Plan

### Provider Configuration Tests

- Default settings return `MockLLMClient`.
- `openai` builds a `ChatModelLLMClient` with the configured model and API key.
- `deepseek` builds a `ChatModelLLMClient` with the configured model and API key.
- Missing provider API key raises a clear configuration error.
- Empty real-provider model raises a clear configuration error.
- Unknown provider raises a clear configuration error.

### Prompt Contract Tests

- Risk prompt includes `risk_analysis:v1`.
- Risk prompt includes source IDs and filing metadata.
- Risk prompt includes the required schema.
- Report prompt includes `report_drafting:v1`.
- Report prompt includes `business_overview` evidence.
- Report prompt includes known `sources`.
- Report prompt excludes secrets and local environment details.

### Output Validation Tests

- Invalid JSON raises `LLMClientError`.
- Non-object JSON raises `LLMClientError`.
- Empty risk themes raise `LLMClientError`.
- Blank risk theme fields raise `LLMClientError`.
- Invalid report sections raise `LLMClientError`.
- Citationless report drafts fall back to deterministic generation.
- Unsafe report drafts are rewritten or blocked by compliance.

### Graph and Persistence Tests

- Injected fake LLM clients can be used for risk and report drafting.
- Failed provider calls record `llm_*_unavailable` warnings.
- Skipped provider calls record skipped call events.
- Completed provider calls record completed call events with prompt version and
  timing.
- Usage metadata is normalized and persisted where available.
- `/research/{run_id}/llm-calls` returns stored events.
- `/research/{run_id}/llm-usage` returns usage rollups.

### Live Smoke Tests

- `tests/test_live_llm.py` remains opt-in.
- Live risk analysis smoke test asserts schema shape and non-empty text fields.
- Live report drafting smoke test asserts schema shape and source citation
  behavior.
- Live SEC plus LLM agent smoke test is opt-in and avoids exact prose
  assertions.

### Documentation Tests

- README documents provider configuration.
- README documents live smoke test flags.
- README documents safe agent testing order: mock first, provider smoke second,
  end-to-end live run last.
- Agent docs identify Stage 4P status and remaining work.

## Definition of Done

Stage 4P is done when:

- The 4P spec exists and matches implemented behavior.
- Provider configuration hardening is covered by deterministic tests.
- Prompt/evidence contracts are covered by deterministic tests.
- LLM output validation and fallback behavior are covered by deterministic
  tests.
- Live provider tests are opt-in and skipped by default.
- End-to-end agent testing is documented or covered by an opt-in live smoke
  test.
- LLM diagnostics remain persisted and available through API endpoints.
- Final reports still pass compliance and report quality validation.
- No normal test requires real SEC or real LLM network access.
- README and agent docs explain safe model API testing.
- `uv run pytest` and `uv run ruff check .` pass.
