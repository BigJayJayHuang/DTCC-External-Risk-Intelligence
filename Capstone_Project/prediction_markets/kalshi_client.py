"""Minimal read-only client for Kalshi's public market-data API (standard library only).

No account or API key is needed for these endpoints. Prices come back as dollar strings
("0.6800" = 68% implied probability); sizes and volumes as fixed-point strings.
Docs: https://docs.kalshi.com/getting_started/quick_start_market_data
"""
from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"   # also accepted: https://api.elections.kalshi.com/trade-api/v2
USER_AGENT = "RiskHorizon-capstone/0.1 (DTCC x Duke; read-only market data)"


class KalshiError(RuntimeError):
    pass


def to_float(v, default=None):
    """Kalshi sends prices/volumes as strings ("0.6800", "1234.00"). Missing or blank -> default."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class KalshiClient:
    def __init__(self, base_url: str = BASE_URL, min_interval: float = 0.12, retries: int = 4, timeout: int = 30, opener=None):
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval      # ~8 requests/s, well under the basic-tier read limit
        self.retries = retries
        self.timeout = timeout
        self._last = 0.0
        self._open = opener or urlopen        # injectable for offline tests

    # ---- low level ----
    def get(self, path: str, params: dict | None = None) -> dict:
        q = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{self.base_url}{path}" + (f"?{urlencode(q)}" if q else "")
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                with self._open(Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}), timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except HTTPError as e:
                if e.code == 429 and attempt < self.retries:   # rate limited: no Retry-After header, so back off
                    time.sleep(2 ** attempt)
                    continue
                if e.code == 404:
                    raise KalshiError(f"404 Not Found: {url}") from e
                if 500 <= e.code < 600 and attempt < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                raise KalshiError(f"HTTP {e.code} for {url}") from e
            except URLError as e:
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                raise KalshiError(f"Network error for {url}: {e.reason}") from e
        raise KalshiError(f"Gave up on {url}")

    def paged(self, path: str, key: str, params: dict | None = None, page_size: int = 1000, max_pages: int = 50) -> list[dict]:
        out, cursor = [], None
        for _ in range(max_pages):
            data = self.get(path, {**(params or {}), "limit": page_size, "cursor": cursor})
            out.extend(data.get(key) or [])
            cursor = data.get("cursor")
            if not cursor:
                break
        return out

    # ---- endpoints ----
    def series(self, series_ticker: str) -> dict:
        return self.get(f"/series/{series_ticker}").get("series") or {}

    def all_series(self, category: str | None = None) -> list[dict]:
        data = self.get("/series", {"category": category})
        return data.get("series") or []

    def markets(self, series_ticker: str | None = None, event_ticker: str | None = None, status: str | None = None) -> list[dict]:
        return self.paged("/markets", "markets", {"series_ticker": series_ticker, "event_ticker": event_ticker, "status": status})

    def historical_markets(self, series_ticker: str | None = None, event_ticker: str | None = None) -> list[dict]:
        """Settled markets older than the historical cutoff (GET /historical/cutoff) live here, not under /markets."""
        try:
            return self.paged("/historical/markets", "markets", {"series_ticker": series_ticker, "event_ticker": event_ticker})
        except KalshiError:
            return []

    def open_events(self) -> list[dict]:
        """All open events with their markets nested (one paged call; the events endpoint caps pages at 200)."""
        return self.paged("/events", "events", {"status": "open", "with_nested_markets": "true"}, page_size=200, max_pages=200)

    def markets_closed_since(self, min_close_ts: int) -> list[dict]:
        """Markets that closed or settled after min_close_ts (for point-in-time snapshots of past weeks).
        Combo/parlay markets are excluded server side; older settled markets are read from /historical/markets."""
        out, seen = [], set()
        for status in ("closed", "settled"):
            for m in self.paged("/markets", "markets", {"status": status, "min_close_ts": int(min_close_ts), "mve_filter": "exclude"},
                                max_pages=200):
                if m.get("ticker") not in seen:
                    seen.add(m.get("ticker")); out.append(m)
        try:
            for m in self.paged("/historical/markets", "markets", {"min_close_ts": int(min_close_ts), "mve_filter": "exclude"}, max_pages=200):
                if m.get("ticker") not in seen:
                    seen.add(m.get("ticker")); out.append(m)
        except KalshiError:
            pass
        return out

    def event(self, event_ticker: str) -> dict:
        return self.get(f"/events/{event_ticker}", {"with_nested_markets": "false"}).get("event") or {}

    def candles(self, series_ticker: str, market_ticker: str, start_ts: int, end_ts: int, period_interval: int = 1440) -> list[dict]:
        """Daily (1440) / hourly (60) / minute (1) candles. Falls back to the historical endpoint for old settled markets."""
        params = {"start_ts": int(start_ts), "end_ts": int(end_ts), "period_interval": period_interval}
        try:
            data = self.get(f"/series/{series_ticker}/markets/{market_ticker}/candlesticks", params)
        except KalshiError as e:
            if "404" not in str(e):
                raise
            data = self.get(f"/historical/markets/{market_ticker}/candlesticks", params)
        return data.get("candlesticks") or []


# ---- parsing helpers (pure functions, unit-tested) ----
def market_prob(m: dict) -> float | None:
    """Implied probability of YES: mid of bid/ask when both quoted, else last trade, else previous price."""
    bid, ask = to_float(m.get("yes_bid_dollars")), to_float(m.get("yes_ask_dollars"))
    if bid is not None and ask is not None and ask > 0 and ask >= bid:
        return round((bid + ask) / 2, 4)
    for k in ("last_price_dollars", "previous_price_dollars"):
        v = to_float(m.get(k))
        if v is not None and v > 0:
            return round(v, 4)
    return None


def market_label(m: dict) -> str:
    """Human label of the outcome (yes_sub_title is the current field; title/subtitle are deprecated fallbacks)."""
    return m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or m.get("ticker", "")


def candle_close(c: dict) -> float | None:
    p = c.get("price") or {}
    v = to_float(p.get("close_dollars"))
    if v is None:   # no trade that period: use the mid of the yes bid/ask closes
        b, a = to_float((c.get("yes_bid") or {}).get("close_dollars")), to_float((c.get("yes_ask") or {}).get("close_dollars"))
        if b is not None and a is not None and a >= b:
            v = (a + b) / 2
    return v
