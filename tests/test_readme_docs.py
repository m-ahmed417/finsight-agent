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
