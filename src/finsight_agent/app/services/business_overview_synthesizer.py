from typing import Any

LATEST_10K_SOURCE_ID = "latest_10k"


def synthesize_business_overview(
    *,
    company_name: str,
    ticker: str,
    business_sections: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not business_sections:
        return {
            "status": "limited",
            "summary": (
                f"{company_name} ({ticker}) business overview is limited to "
                "resolved company identity because Item 1 Business evidence was "
                "not available in this run."
            ),
            "source_ids": [],
            "limitations": _business_limitations(warnings),
        }

    section = business_sections[0]
    source_form = str(section.get("form") or "10-K")
    filing_date = str(section.get("filing_date") or "unknown filing date")
    accession_number = str(section.get("accession_number") or "unknown accession")
    return {
        "status": "available",
        "summary": (
            f"{company_name} ({ticker}) has Item 1 Business evidence from the "
            f"latest {source_form} filed {filing_date}. Use this SEC filing "
            "evidence for company overview context without adding external "
            "company descriptions."
        ),
        "source": (
            f"{source_form} filed {filing_date}, accession {accession_number}"
        ),
        "source_ids": _source_ids(section),
        "source_form": source_form,
        "filing_date": filing_date,
        "accession_number": accession_number,
        "source_url": section.get("source_url"),
        "section": str(section.get("section") or "Item 1"),
        "section_label": str(section.get("section_label") or "Business"),
        "text_character_count": _text_character_count(section),
        "limitations": [],
    }


def _business_limitations(warnings: list[dict[str, Any]]) -> list[str]:
    limitations = [
        str(warning.get("message"))
        for warning in warnings
        if warning.get("code")
        in {"business_section_unavailable", "filing_text_unavailable"}
        and warning.get("message")
    ]
    if limitations:
        return limitations
    return ["Item 1 Business evidence was not available in this run."]


def _source_ids(section: dict[str, Any]) -> list[str]:
    source_ids = section.get("source_ids")
    if isinstance(source_ids, list):
        normalized = [
            source_id
            for value in source_ids
            if (source_id := str(value).strip())
        ]
        if normalized:
            return normalized

    source_id = str(section.get("source_id") or "").strip()
    if source_id:
        return [source_id]
    return [LATEST_10K_SOURCE_ID]


def _text_character_count(section: dict[str, Any]) -> int:
    value = section.get("text_character_count")
    if isinstance(value, int) and value >= 0:
        return value
    text = section.get("text")
    return len(text) if isinstance(text, str) else 0
