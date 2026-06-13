from typing import Any

import httpx


class SECClientError(RuntimeError):
    """Raised when the SEC client cannot return a usable response."""


class SECClient:
    COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
    COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

    def __init__(self, user_agent: str, timeout: float = 10.0) -> None:
        normalized_user_agent = user_agent.strip()
        if not normalized_user_agent:
            msg = "SEC user agent cannot be empty."
            raise ValueError(msg)

        self._user_agent = normalized_user_agent
        self._timeout = timeout

    def fetch_company_tickers(self) -> dict[str, Any]:
        response = self._get(self.COMPANY_TICKERS_URL)
        return self._parse_json(response, source="company tickers")

    def fetch_company_submissions(self, cik: str) -> dict[str, Any]:
        normalized_cik = self._normalize_cik(cik)
        url = self.SUBMISSIONS_URL_TEMPLATE.format(cik=normalized_cik)
        response = self._get(url)
        return self._parse_json(response, source="company submissions")

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        normalized_cik = self._normalize_cik(cik)
        url = self.COMPANY_FACTS_URL_TEMPLATE.format(cik=normalized_cik)
        response = self._get(url)
        return self._parse_json(response, source="company facts")

    def _get(self, url: str) -> httpx.Response:
        try:
            response = httpx.get(
                url,
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            msg = f"SEC request failed for {url}: {exc}"
            raise SECClientError(msg) from exc

        if response.status_code >= 400:
            msg = f"SEC request failed with status {response.status_code} for {url}."
            raise SECClientError(msg)

        return response

    def _parse_json(self, response: httpx.Response, source: str) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            msg = f"SEC {source} response contained malformed JSON."
            raise SECClientError(msg) from exc

        if not isinstance(data, dict):
            msg = f"SEC {source} response must be a JSON object."
            raise SECClientError(msg)

        return data

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }

    @staticmethod
    def _normalize_cik(cik: str) -> str:
        digits = "".join(char for char in str(cik).strip() if char.isdigit())
        if not digits:
            msg = "CIK must contain at least one digit."
            raise ValueError(msg)
        return digits.zfill(10)
