import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, TypeVar

import httpx


ResponseDataT = TypeVar("ResponseDataT")


@dataclass(frozen=True)
class SECResponseMetadata:
    url: str
    cache_status: str
    cache_key: str | None = None
    cache_age_seconds: float | None = None
    cache_ttl_seconds: float | None = None
    cache_expires_at: str | None = None
    cache_stale: bool | None = None


@dataclass(frozen=True)
class SECClientResult(Generic[ResponseDataT]):
    data: ResponseDataT
    metadata: SECResponseMetadata


@dataclass(frozen=True)
class _CacheEntry:
    text: str
    modified_at: float


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
        cache_ttl_seconds: float | None = None,
        min_request_interval_seconds: float = 0.0,
        clock: Callable[[], float] | None = None,
        wall_clock: Callable[[], float] | None = None,
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
        if cache_ttl_seconds is not None and cache_ttl_seconds < 0:
            msg = "SEC cache_ttl_seconds cannot be negative."
            raise ValueError(msg)

        self._user_agent = normalized_user_agent
        self._timeout = timeout
        self._max_retries = max_retries
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._cache_ttl_seconds = cache_ttl_seconds
        self._min_request_interval_seconds = min_request_interval_seconds
        self._clock = clock or time.monotonic
        self._wall_clock = wall_clock or time.time
        self._sleep = sleep or time.sleep
        self._last_request_started_at: float | None = None

    def fetch_company_tickers(self) -> dict[str, Any]:
        return self.fetch_company_tickers_with_metadata().data

    def fetch_company_tickers_with_metadata(self) -> SECClientResult[dict[str, Any]]:
        return self._get_json_with_metadata(
            self.COMPANY_TICKERS_URL,
            source="company tickers",
            cache_key="company_tickers",
        )

    def fetch_company_submissions(self, cik: str) -> dict[str, Any]:
        return self.fetch_company_submissions_with_metadata(cik).data

    def fetch_company_submissions_with_metadata(
        self,
        cik: str,
    ) -> SECClientResult[dict[str, Any]]:
        normalized_cik = self._normalize_cik(cik)
        url = self.SUBMISSIONS_URL_TEMPLATE.format(cik=normalized_cik)
        return self._get_json_with_metadata(
            url,
            source="company submissions",
            cache_key=f"company_submissions:{normalized_cik}",
        )

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        return self.fetch_company_facts_with_metadata(cik).data

    def fetch_company_facts_with_metadata(
        self,
        cik: str,
    ) -> SECClientResult[dict[str, Any]]:
        normalized_cik = self._normalize_cik(cik)
        url = self.COMPANY_FACTS_URL_TEMPLATE.format(cik=normalized_cik)
        return self._get_json_with_metadata(
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
        return self.fetch_filing_document_with_metadata(
            cik=cik,
            accession_number=accession_number,
            primary_document=primary_document,
        ).data

    def fetch_filing_document_with_metadata(
        self,
        *,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> SECClientResult[str]:
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
        return self._get_text_with_metadata(
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
        return self._get_json_with_metadata(
            url,
            source=source,
            cache_key=cache_key,
        ).data

    def _get_json_with_metadata(
        self,
        url: str,
        *,
        source: str,
        cache_key: str,
    ) -> SECClientResult[dict[str, Any]]:
        cache_entry = self._read_cache_entry(cache_key)
        if cache_entry is not None and not self._cache_entry_is_stale(cache_entry):
            return SECClientResult(
                data=self._parse_json_text(cache_entry.text, source=source),
                metadata=self._cache_metadata(
                    url=url,
                    cache_key=cache_key,
                    cache_status="hit",
                    cache_entry=cache_entry,
                ),
            )

        response = self._get(url)
        data = self._parse_json(response, source=source)
        self._write_cache_text(cache_key, response.text)
        return SECClientResult(
            data=data,
            metadata=self._live_response_cache_metadata(
                url=url,
                cache_key=cache_key,
            ),
        )

    def _get_text(
        self,
        url: str,
        *,
        headers: dict[str, str],
        cache_key: str,
    ) -> str:
        return self._get_text_with_metadata(
            url,
            headers=headers,
            cache_key=cache_key,
        ).data

    def _get_text_with_metadata(
        self,
        url: str,
        *,
        headers: dict[str, str],
        cache_key: str,
    ) -> SECClientResult[str]:
        cache_entry = self._read_cache_entry(cache_key)
        if cache_entry is not None and not self._cache_entry_is_stale(cache_entry):
            return SECClientResult(
                data=cache_entry.text,
                metadata=self._cache_metadata(
                    url=url,
                    cache_key=cache_key,
                    cache_status="hit",
                    cache_entry=cache_entry,
                ),
            )

        response = self._get(url, headers=headers)
        self._write_cache_text(cache_key, response.text)
        return SECClientResult(
            data=response.text,
            metadata=self._live_response_cache_metadata(url=url, cache_key=cache_key),
        )

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
        cache_entry = self._read_cache_entry(cache_key)
        if cache_entry is None:
            return None
        return cache_entry.text

    def _read_cache_entry(self, cache_key: str) -> _CacheEntry | None:
        if self._cache_dir is None:
            return None

        cache_path = self._cache_path(cache_key)
        if not cache_path.exists():
            return None

        try:
            return _CacheEntry(
                text=cache_path.read_text(encoding="utf-8"),
                modified_at=cache_path.stat().st_mtime,
            )
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

    def _live_response_cache_metadata(
        self,
        *,
        url: str,
        cache_key: str,
    ) -> SECResponseMetadata:
        if self._cache_dir is None:
            return self._cache_metadata(
                url=url,
                cache_key=None,
                cache_status="disabled",
            )
        cache_entry = self._read_cache_entry(cache_key)
        return self._cache_metadata(
            url=url,
            cache_key=cache_key,
            cache_status="miss",
            cache_entry=cache_entry,
        )

    def _cache_metadata(
        self,
        *,
        url: str,
        cache_key: str | None,
        cache_status: str,
        cache_entry: _CacheEntry | None = None,
    ) -> SECResponseMetadata:
        freshness = self._cache_freshness_metadata(cache_entry)
        return SECResponseMetadata(
            url=url,
            cache_key=cache_key,
            cache_status=cache_status,
            **freshness,
        )

    def _cache_freshness_metadata(
        self,
        cache_entry: _CacheEntry | None,
    ) -> dict[str, Any]:
        if cache_entry is None:
            return {}

        age_seconds = max(0.0, self._wall_clock() - cache_entry.modified_at)
        freshness: dict[str, Any] = {
            "cache_age_seconds": age_seconds,
        }
        if self._cache_ttl_seconds is None:
            return freshness

        expires_at = cache_entry.modified_at + self._cache_ttl_seconds
        freshness.update(
            {
                "cache_ttl_seconds": self._cache_ttl_seconds,
                "cache_expires_at": datetime.fromtimestamp(
                    expires_at,
                    timezone.utc,
                ).isoformat(),
                "cache_stale": age_seconds > self._cache_ttl_seconds,
            }
        )
        return freshness

    def _cache_entry_is_stale(self, cache_entry: _CacheEntry) -> bool:
        if self._cache_ttl_seconds is None:
            return False
        age_seconds = max(0.0, self._wall_clock() - cache_entry.modified_at)
        return age_seconds > self._cache_ttl_seconds

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
