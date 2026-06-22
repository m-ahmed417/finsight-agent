from pathlib import Path


def test_readme_documents_background_research_polling_workflow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "## API Workflow" in readme
    section = readme.split("## API Workflow", maxsplit=1)[1]

    required_phrases = [
        "POST /research",
        "202 Accepted",
        "run_id",
        "queued",
        "running",
        "completed",
        "failed",
        "GET /research/{run_id}",
        "GET /research/{run_id}/progress",
        "GET /research/{run_id}/steps",
        "GET /research/{run_id}/llm-calls",
        "GET /research/{run_id}/llm-usage",
        "errors",
        "agent_steps",
        "llm_call_events",
        "latest_step",
        "started_at",
        "completed_at",
        "duration_seconds",
        "llm_provider",
        "llm_model",
        "llm_used",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_version",
        "provider_request_id",
        "fallback_used",
        "completed_calls",
        "failed_calls",
        "skipped_calls",
        "fallback_count",
        "total_input_tokens",
        "total_output_tokens",
    ]
    for phrase in required_phrases:
        assert phrase in section


def test_readme_documents_research_lifecycle_timing_and_recovery() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "## API Workflow" in readme
    assert "## Configuration" in readme
    workflow_section = readme.split("## API Workflow", maxsplit=1)[1].split(
        "## Configuration",
        maxsplit=1,
    )[0]
    configuration_section = readme.split("## Configuration", maxsplit=1)[1]

    for phrase in [
        "created_at",
        "completed_at",
        "duration_seconds",
        "terminal status",
        "research_run_stale",
    ]:
        assert phrase in workflow_section

    for phrase in [
        "RESEARCH_RUN_STALE_AFTER_SECONDS",
        "3600",
        "startup",
        "queued",
        "running",
        "failed",
    ]:
        assert phrase in configuration_section


def test_readme_documents_failed_research_retry_workflow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "## API Workflow" in readme
    assert "## Configuration" in readme
    workflow_section = readme.split("## API Workflow", maxsplit=1)[1].split(
        "## Configuration",
        maxsplit=1,
    )[0]

    for phrase in [
        "POST /research/{run_id}/retry",
        "202 Accepted",
        "404",
        "409",
        "Only failed research runs can be retried",
        "new queued run",
        "original failed run",
        "retried_from_run_id",
        "points to the original failed run",
        "GET /research/{run_id}/retries",
        "retry chain",
        "creation order",
    ]:
        assert phrase in workflow_section


def test_readme_documents_research_run_listing_workflow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "## API Workflow" in readme
    assert "## Configuration" in readme
    workflow_section = readme.split("## API Workflow", maxsplit=1)[1].split(
        "## Configuration",
        maxsplit=1,
    )[0]

    for phrase in [
        "GET /research`",
        "newest-first",
        "status=failed",
        "limit=20",
        "1 and 100",
        "compact summaries",
        "warnings_count",
        "errors_count",
        "has_report",
        "next_cursor",
        "has_more",
        "cursor",
        "Use `GET /research/{run_id}` for detailed fields",
        '"items": [',
        '"next_cursor":',
        '"has_more": true',
        '"warnings_count": 1',
        '"errors_count": 0',
        '"has_report": true',
        "GET /research?status=failed&limit=20&cursor={next_cursor}",
    ]:
        assert phrase in workflow_section


def test_readme_documents_report_quality_and_grounding() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "### Report Quality and Grounding" in readme
    workflow_section = readme.split("### Report Quality and Grounding", maxsplit=1)[1]

    for phrase in [
        "11-section structure",
        "research-only disclaimer",
        "not financial advice",
        "Item 1 Business",
        "Company Overview",
        "raw Item 1 text",
        "`[sec_company_facts]`",
        "`[latest_10k]`",
        "warnings or limitations",
        "compliance_status",
        "report_quality_status",
        'report_quality_status="passed"',
        "MVP draft",
        "future versions will",
        "pending deterministic synthesis",
        "no sources were recorded",
    ]:
        assert phrase in workflow_section


def test_agent_docs_document_stage_4o_completion() -> None:
    docs = {
        "AGENTS.md": Path("AGENTS.md").read_text(encoding="utf-8"),
        "docs/AGENTS_FULL.md": Path("docs/AGENTS_FULL.md").read_text(
            encoding="utf-8"
        ),
    }

    for path, text in docs.items():
        assert "4O - Business Overview and Filing Evidence" in text, path
        assert "docs/specs/4O-business-overview-filing-evidence.md" in text, path
        assert "Item 1 Business" in text, path
        assert "business_overview" in text, path
        assert "Company Overview" in text, path
        assert "raw Item 1 text" in text, path


def test_readme_documents_llm_provider_testing_workflow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "## Configuration" in readme
    assert "### Live Smoke Tests" in readme
    configuration_section = readme.split("## Configuration", maxsplit=1)[1]
    live_section = readme.split("### Live Smoke Tests", maxsplit=1)[1]

    for phrase in [
        "LLM_PROVIDER=mock",
        "LLM_PROVIDER=openai",
        "LLM_PROVIDER=deepseek",
        "LLM_MODEL",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "real providers require a non-empty `LLM_MODEL`",
        "do not store API keys in committed files",
    ]:
        assert phrase in configuration_section

    for phrase in [
        "RUN_LIVE_LLM_TESTS",
        "RUN_LIVE_SEC_LLM_GRAPH_TESTS",
        "tests/test_live_sec_llm_graph.py",
        "provider-backed risk analysis and report drafting",
        "mock first",
        "provider smoke test second",
        "end-to-end live run last",
        "LLM call events",
        "usage summary",
        "deterministic fallback",
        "skipped by default",
        "normal CI",
    ]:
        assert phrase in live_section


def test_readme_documents_financial_presentation_and_period_analysis() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "### Financial Presentation and Period Analysis" in readme
    section = readme.split(
        "### Financial Presentation and Period Analysis",
        maxsplit=1,
    )[1]

    for phrase in [
        "`$1.25B`",
        "`$280.0M`",
        "`25.0%`",
        "`N/A`",
        "raw numeric metric values remain internal",
        "deterministic period comparisons",
        "`[sec_company_facts]`",
        "LLM report drafts that repeat raw metric values",
        "deterministic fallback",
    ]:
        assert phrase in section


def test_readme_documents_filing_evidence_robustness() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "### Filing Evidence Robustness" in readme
    section = readme.split("### Filing Evidence Robustness", maxsplit=1)[1]

    for phrase in [
        "deterministic filing extraction",
        "Item 1 Business",
        "Item 1A Risk Factors",
        "heading variants",
        "`PART I`",
        "table-of-contents",
        "non-breaking spaces",
        "Item 1B",
        "Item 2",
        "extraction_diagnostics",
        "candidate_count",
        "selection_reason",
        "warning_reason",
        "business_section_unavailable",
        "risk_factors_unavailable",
        "warnings or limitations",
        "`[latest_10k]`",
        "not use LLMs",
    ]:
        assert phrase in section


def test_readme_documents_report_citation_audit_and_quality_details() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "### Report Citation Audit and Quality Details" in readme
    section = readme.split(
        "### Report Citation Audit and Quality Details",
        maxsplit=1,
    )[1]

    for phrase in [
        "deterministic citation audit",
        "report_quality_details",
        "citation_audit",
        "known_source_ids",
        "unknown_citations",
        "sections_missing_required_citations",
        "missing_required_sections",
        "section-level",
        "`[sec_company_facts]`",
        "`[latest_10k]`",
        "LLM report drafts",
        "missing or unknown citations",
        "deterministic fallback",
        "not use LLMs",
    ]:
        assert phrase in section


def test_agent_docs_document_stage_4p_provider_testing_status() -> None:
    docs = {
        "AGENTS.md": Path("AGENTS.md").read_text(encoding="utf-8"),
        "docs/AGENTS_FULL.md": Path("docs/AGENTS_FULL.md").read_text(
            encoding="utf-8"
        ),
    }

    for path, text in docs.items():
        assert "4P - LLM Provider Integration and Agent Testing" in text, path
        assert "docs/specs/4P-llm-provider-integration-agent-testing.md" in text, path
        assert "provider smoke test" in text, path
        assert "RUN_LIVE_LLM_TESTS" in text, path
        assert "RUN_LIVE_SEC_LLM_GRAPH_TESTS" in text, path
        assert "mock first" in text, path
        assert "end-to-end live run last" in text, path
        assert "report drafting" in text, path
        assert "4P-5" in text, path


def test_agent_docs_document_stage_4q_financial_presentation_status() -> None:
    docs = {
        "AGENTS.md": Path("AGENTS.md").read_text(encoding="utf-8"),
        "docs/AGENTS_FULL.md": Path("docs/AGENTS_FULL.md").read_text(
            encoding="utf-8"
        ),
    }

    for path, text in docs.items():
        assert "4Q - Financial Presentation and Period Analysis" in text, path
        assert "docs/specs/4Q-financial-presentation-period-analysis.md" in text, path
        assert "financial_presentation" in text, path
        assert "readable financial values" in text, path
        assert "deterministic period comparisons" in text, path
        assert "raw metric values" in text, path
        assert "LLM report draft financial performance" in text, path
        assert "4Q-5" in text, path


def test_agent_docs_document_stage_4r_filing_robustness_status() -> None:
    docs = {
        "AGENTS.md": Path("AGENTS.md").read_text(encoding="utf-8"),
        "docs/AGENTS_FULL.md": Path("docs/AGENTS_FULL.md").read_text(
            encoding="utf-8"
        ),
    }

    for path, text in docs.items():
        assert "4R - Filing Evidence Robustness" in text, path
        assert "docs/specs/4R-filing-evidence-robustness.md" in text, path
        assert "deterministic filing extraction" in text, path
        assert "heading variants" in text, path
        assert "table-of-contents" in text, path
        assert "extraction_diagnostics" in text, path
        assert "business_section_unavailable" in text, path
        assert "risk_factors_unavailable" in text, path
        assert "4R-5" in text, path


def test_agent_docs_document_stage_4s_citation_audit_status() -> None:
    docs = {
        "AGENTS.md": Path("AGENTS.md").read_text(encoding="utf-8"),
        "docs/AGENTS_FULL.md": Path("docs/AGENTS_FULL.md").read_text(
            encoding="utf-8"
        ),
    }

    for path, text in docs.items():
        assert "4S - Report Citation Audit and Quality Details" in text, path
        assert "docs/specs/4S-report-citation-audit-quality-details.md" in text, path
        assert "report_quality_details" in text, path
        assert "citation_audit" in text, path
        assert "known_source_ids" in text, path
        assert "unknown_citations" in text, path
        assert "sections_missing_required_citations" in text, path
        assert "LLM report draft" in text, path
        assert "4S-5" in text, path
