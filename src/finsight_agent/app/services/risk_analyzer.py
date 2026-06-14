from typing import Any

RISK_THEME_RULES = (
    {
        "title": "Competitive pressure",
        "keywords": ("competition", "competitive"),
        "summary": (
            "The filing describes competition as a material business risk that "
            "could pressure operating performance."
        ),
    },
    {
        "title": "Supply chain and manufacturing disruption",
        "keywords": ("supply chain", "component", "manufacturing"),
        "summary": (
            "The filing indicates that supply chain disruption, component "
            "availability, or manufacturing delays could affect operations."
        ),
    },
    {
        "title": "Third-party platform and distribution dependence",
        "keywords": ("third-party", "software", "distribution"),
        "summary": (
            "The filing notes dependence on third-party software, services, or "
            "distribution channels as an operating risk."
        ),
    },
    {
        "title": "Regulatory and legal exposure",
        "keywords": ("regulation", "regulatory", "legal", "litigation"),
        "summary": (
            "The filing identifies regulatory, legal, or litigation exposure as a "
            "risk that could affect the business."
        ),
    },
    {
        "title": "Macroeconomic sensitivity",
        "keywords": ("macroeconomic", "economic conditions", "inflation", "interest rate"),
        "summary": (
            "The filing describes macroeconomic conditions as a factor that could "
            "affect demand, costs, or operating results."
        ),
    },
)


def analyze_risk_factors(risk_factors: list[dict[str, Any]]) -> dict[str, Any]:
    if not risk_factors:
        return {
            "themes": [],
            "warnings": [
                {
                    "code": "risk_analysis_unavailable",
                    "message": "Risk-factor text was unavailable for analysis.",
                    "severity": "warning",
                }
            ],
        }

    themes: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for risk_factor in risk_factors:
        text = str(risk_factor.get("text", "")).casefold()
        if not text:
            continue

        for rule in RISK_THEME_RULES:
            title = rule["title"]
            if title in seen_titles:
                continue
            if any(keyword in text for keyword in rule["keywords"]):
                themes.append(_theme_from_rule(rule, risk_factor))
                seen_titles.add(title)

    warnings = []
    if not themes:
        warnings.append(
            {
                "code": "risk_analysis_unavailable",
                "message": "No deterministic risk themes matched the extracted risk text.",
                "severity": "warning",
            }
        )

    return {"themes": themes, "warnings": warnings}


def _theme_from_rule(rule: dict[str, Any], risk_factor: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": rule["title"],
        "summary": rule["summary"],
        "source_form": risk_factor.get("form"),
        "filing_date": risk_factor.get("filing_date"),
        "accession_number": risk_factor.get("accession_number"),
        "source_url": risk_factor.get("source_url"),
    }
