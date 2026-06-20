from types import SimpleNamespace

from finsight_agent.app.services.llm_usage import summarize_llm_usage


def test_summarize_llm_usage_rolls_up_counts_tokens_and_identity() -> None:
    summary = summarize_llm_usage(
        [
            SimpleNamespace(
                status="completed",
                llm_provider="openai",
                llm_model="gpt-test-model",
                duration_seconds=1.25,
                input_tokens=120,
                output_tokens=42,
                total_tokens=162,
                fallback_used=False,
            ),
            SimpleNamespace(
                status="failed",
                llm_provider="openai",
                llm_model="gpt-test-model",
                duration_seconds=2.0,
                input_tokens=300,
                output_tokens=None,
                total_tokens=None,
                fallback_used=True,
            ),
            SimpleNamespace(
                status="skipped",
                llm_provider=None,
                llm_model=None,
                duration_seconds=None,
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                fallback_used=True,
            ),
            {
                "status": "completed",
                "llm_provider": "deepseek",
                "llm_model": "deepseek-test-model",
                "duration_seconds": 0.5,
                "input_tokens": 50,
                "output_tokens": 10,
                "total_tokens": 60,
                "fallback_used": False,
            },
        ]
    )

    assert summary == {
        "total_calls": 4,
        "completed_calls": 2,
        "failed_calls": 1,
        "skipped_calls": 1,
        "fallback_count": 2,
        "total_duration_seconds": 3.75,
        "total_input_tokens": 470,
        "total_output_tokens": 52,
        "total_tokens": 222,
        "providers": ["deepseek", "openai"],
        "models": ["deepseek-test-model", "gpt-test-model"],
    }


def test_summarize_llm_usage_returns_zero_summary_for_no_events() -> None:
    assert summarize_llm_usage([]) == {
        "total_calls": 0,
        "completed_calls": 0,
        "failed_calls": 0,
        "skipped_calls": 0,
        "fallback_count": 0,
        "total_duration_seconds": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "providers": [],
        "models": [],
    }
