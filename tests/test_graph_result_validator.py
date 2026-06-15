import pytest

from finsight_agent.app.services.graph_result_validator import (
    GraphResultValidationError,
    validate_graph_result,
)


def test_validate_graph_result_normalizes_contract_fields_without_mutating_input() -> None:
    graph_result = {
        "ticker": "AAPL",
        "warnings": [
            {
                "code": " metric_warning ",
                "message": "Revenue could not be extracted.",
            }
        ],
        "errors": [
            {
                "code": " company_not_found ",
                "message": "Could not confidently resolve the company.",
            }
        ],
        "sources": [
            {
                "source_id": " sec_company_facts ",
                "source_type": "sec_company_facts",
                "label": "SEC company facts",
                "metric_fiscal_years": [2023, 2024],
                "xbrl_tags_used": [
                    "RevenueFromContractWithCustomerExcludingAssessedTax"
                ],
                "cache_status": "hit",
            }
        ],
        "agent_steps": [
            {
                "node_name": " fetch_sec_data ",
                "status": " completed ",
                "message": "Fetched SEC submissions and company facts.",
                "duration_ms": 125,
            }
        ],
    }

    normalized = validate_graph_result(graph_result)

    assert normalized is not graph_result
    assert graph_result["warnings"][0]["code"] == " metric_warning "
    assert normalized["ticker"] == "AAPL"
    assert normalized["warnings"] == [
        {
            "code": "metric_warning",
            "message": "Revenue could not be extracted.",
            "severity": "warning",
        }
    ]
    assert normalized["errors"] == [
        {
            "code": "company_not_found",
            "message": "Could not confidently resolve the company.",
            "severity": "error",
        }
    ]
    assert normalized["sources"] == [
        {
            "source_id": "sec_company_facts",
            "source_type": "sec_company_facts",
            "label": "SEC company facts",
            "metric_fiscal_years": [2023, 2024],
            "xbrl_tags_used": [
                "RevenueFromContractWithCustomerExcludingAssessedTax"
            ],
            "cache_status": "hit",
        }
    ]
    assert normalized["agent_steps"] == [
        {
            "node_name": "fetch_sec_data",
            "status": "completed",
            "message": "Fetched SEC submissions and company facts.",
            "duration_ms": 125,
        }
    ]


def test_validate_graph_result_defaults_missing_contract_lists() -> None:
    normalized = validate_graph_result({"ticker": "AAPL"})

    assert normalized["warnings"] == []
    assert normalized["errors"] == []
    assert normalized["sources"] == []
    assert normalized["agent_steps"] == []


def test_validate_graph_result_rejects_non_mapping_result() -> None:
    with pytest.raises(GraphResultValidationError, match="must be a mapping"):
        validate_graph_result([])


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("warnings", {}),
        ("errors", {}),
        ("sources", {}),
        ("agent_steps", {}),
    ],
)
def test_validate_graph_result_rejects_non_list_contract_fields(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(
        GraphResultValidationError,
        match=f"Graph result field '{field_name}' must be a list.",
    ):
        validate_graph_result({field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value", "expected_message"),
    [
        (
            "warnings",
            [{"code": "metric_warning", "message": " "}],
            "Invalid graph result field 'warnings' item 0: message:",
        ),
        (
            "errors",
            [{"code": "company_not_found", "message": " "}],
            "Invalid graph result field 'errors' item 0: message:",
        ),
        (
            "sources",
            [{"source_id": " "}],
            "Invalid graph result field 'sources' item 0: source_id:",
        ),
        (
            "agent_steps",
            [{"node_name": "resolve_company", "status": " "}],
            "Invalid graph result field 'agent_steps' item 0: status:",
        ),
    ],
)
def test_validate_graph_result_reports_field_and_index_for_invalid_items(
    field_name: str,
    value: list[dict[str, str]],
    expected_message: str,
) -> None:
    with pytest.raises(GraphResultValidationError, match=expected_message):
        validate_graph_result({field_name: value})
