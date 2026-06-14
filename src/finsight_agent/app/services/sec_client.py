from typing import Any

import httpx


class SECClientError(RuntimeError):
    """Raised when the SEC client cannot return a usable response."""


class SECClient:
    COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
    COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    FILING_DOCUMENT_URL_TEMPLATE = (
        "https://www.sec.gov/Archives/edgar/data/"
        "{cik_path}/{accession_path}/{primary_document}"
    )

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

    def fetch_filing_document(
        self,
        *,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> str:
        normalized_cik = self._normalize_cik(cik)
        normalized_primary_document = primary_document.strip()
        if not normalized_primary_document:
            msg = "Primary document cannot be empty."
            raise ValueError(msg)

        url = self.FILING_DOCUMENT_URL_TEMPLATE.format(
            cik_path=str(int(normalized_cik)),
            accession_path=self._normalize_accession_number(accession_number),
            primary_document=normalized_primary_document,
        )
        response = self._get(url, headers=self._document_headers)
        return response.text

    def _get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        try:
            response = httpx.get(
                url,
                headers=headers or self._json_headers,
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
    def _json_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }

    @property
    def _document_headers(self) -> dict[str, str]:
        return {
            "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
            "User-Agent": self._user_agent,
        }

    @staticmethod
    def _normalize_cik(cik: str) -> str:
        digits = "".join(char for char in str(cik).strip() if char.isdigit())
        if not digits:
            msg = "CIK must contain at least one digit."
            raise ValueError(msg)
        return digits.zfill(10)

    @staticmethod
    def _normalize_accession_number(accession_number: str) -> str:
        digits = "".join(char for char in str(accession_number).strip() if char.isdigit())
        if not digits:
            msg = "Accession number must contain at least one digit."
            raise ValueError(msg)
        return digits
