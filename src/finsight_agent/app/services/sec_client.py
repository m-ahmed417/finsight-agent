import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
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

    def __init__(
        self,
        user_agent: str,
        timeout: float = 10.0,
        max_retries: int = 2,
        cache_dir: str | Path | None = None,
        min_request_interval_seconds: float = 0.0,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        normalized_user_agent = user_agent.strip()
        if not normalized_user_agent:
            msg = "SEC user agent cannot be empty."
            raise ValueError(msg)
        if max_retries < 0:
            msg = "SEC max_retries cannot be negative."
            raise ValueError(msg)
        if min_request_interval_seconds < 0:
            msg = "SEC min_request_interval_seconds cannot be negative."
            raise ValueError(msg)

        self._user_agent = normalized_user_agent
        self._timeout = timeout
        self._max_retries = max_retries
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._min_request_interval_seconds = min_request_interval_seconds
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._last_request_started_at: float | None = None

    def fetch_company_tickers(self) -> dict[str, Any]:
        return self._get_json(
            self.COMPANY_TICKERS_URL,
            source="company tickers",
            cache_key="company_tickers",
        )

    def fetch_company_submissions(self, cik: str) -> dict[str, Any]:
        normalized_cik = self._normalize_cik(cik)
        url = self.SUBMISSIONS_URL_TEMPLATE.format(cik=normalized_cik)
        return self._get_json(
            url,
            source="company submissions",
            cache_key=f"company_submissions:{normalized_cik}",
        )

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        normalized_cik = self._normalize_cik(cik)
        url = self.COMPANY_FACTS_URL_TEMPLATE.format(cik=normalized_cik)
        return self._get_json(
            url,
            source="company facts",
            cache_key=f"company_facts:{normalized_cik}",
        )

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
        return self._get_text(
            url,
            headers=self._document_headers,
            cache_key=(
                "filing_document:"
                f"{normalized_cik}:"
                f"{self._normalize_accession_number(accession_number)}:"
                f"{normalized_primary_document}"
            ),
        )

    def _get_json(
        self,
        url: str,
        *,
        source: str,
        cache_key: str,
    ) -> dict[str, Any]:
        cached_text = self._read_cache_text(cache_key)
        if cached_text is not None:
            return self._parse_json_text(cached_text, source=source)

        response = self._get(url)
        data = self._parse_json(response, source=source)
        self._write_cache_text(cache_key, response.text)
        return data

    def _get_text(
        self,
        url: str,
        *,
        headers: dict[str, str],
        cache_key: str,
    ) -> str:
        cached_text = self._read_cache_text(cache_key)
        if cached_text is not None:
            return cached_text

        response = self._get(url, headers=headers)
        self._write_cache_text(cache_key, response.text)
        return response.text

    def _get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        max_attempts = self._max_retries + 1
        request_headers = headers or self._json_headers
        for attempt in range(1, max_attempts + 1):
            try:
                self._apply_rate_limit()
                response = httpx.get(
                    url,
                    headers=request_headers,
                    timeout=self._timeout,
                )
            except httpx.TimeoutException as exc:
                if attempt < max_attempts:
                    continue
                msg = (
                    f"SEC request failed for {url} after {attempt} attempts: "
                    f"{exc}"
                )
                raise SECClientError(msg) from exc
            except httpx.HTTPError as exc:
                msg = f"SEC request failed for {url}: {exc}"
                raise SECClientError(msg) from exc

            if response.status_code >= 500:
                if attempt < max_attempts:
                    continue
                msg = (
                    "SEC request failed with status "
                    f"{response.status_code} for {url} after {attempt} attempts."
                )
                raise SECClientError(msg)

            if response.status_code >= 400:
                msg = f"SEC request failed with status {response.status_code} for {url}."
                raise SECClientError(msg)

            return response

        msg = f"SEC request failed for {url} after {max_attempts} attempts."
        raise SECClientError(msg)

    def _apply_rate_limit(self) -> None:
        if self._min_request_interval_seconds <= 0:
            return

        now = self._clock()
        if self._last_request_started_at is None:
            self._last_request_started_at = now
            return

        elapsed = max(0.0, now - self._last_request_started_at)
        wait_seconds = self._min_request_interval_seconds - elapsed
        if wait_seconds > 0:
            self._sleep(wait_seconds)
            now = self._clock()

        self._last_request_started_at = now

    def _parse_json(self, response: httpx.Response, source: str) -> dict[str, Any]:
        return self._parse_json_text(response.text, source=source)

    def _parse_json_text(self, text: str, *, source: str) -> dict[str, Any]:
        try:
            data = json.loads(text)
        except ValueError as exc:
            msg = f"SEC {source} response contained malformed JSON."
            raise SECClientError(msg) from exc

        if not isinstance(data, dict):
            msg = f"SEC {source} response must be a JSON object."
            raise SECClientError(msg)

        return data

    def _read_cache_text(self, cache_key: str) -> str | None:
        if self._cache_dir is None:
            return None

        cache_path = self._cache_path(cache_key)
        if not cache_path.exists():
            return None

        try:
            return cache_path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _write_cache_text(self, cache_key: str, text: str) -> None:
        if self._cache_dir is None:
            return

        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(cache_key).write_text(text, encoding="utf-8")
        except OSError:
            return

    def _cache_path(self, cache_key: str) -> Path:
        if self._cache_dir is None:
            msg = "SEC cache directory is not configured."
            raise RuntimeError(msg)

        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.cache"

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
