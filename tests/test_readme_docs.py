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
        "GET /research/{run_id}/steps",
        "errors",
        "agent_steps",
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
        "same response shape",
    ]:
        assert phrase in workflow_section
