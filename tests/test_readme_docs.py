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
