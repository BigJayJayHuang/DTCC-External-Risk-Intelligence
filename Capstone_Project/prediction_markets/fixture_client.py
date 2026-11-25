"""Offline stand-in for KalshiClient that reads JSON files from fixtures/ (same method names).

Fixture prices are SIMULATED for tests and demos. They are shaped like real API responses
(dollar strings, fixed-point volumes) but are not real Kalshi prices.
"""
from __future__ import annotations

import json
from pathlib import Path


class FixtureClient:
    def __init__(self, folder):
        self.f = Path(folder)

    def _load(self, name, default):
        p = self.f / name
        return json.loads(p.read_text()) if p.exists() else default

    def markets(self, series_ticker=None, event_ticker=None, status=None):
        ms = self._load(f"markets_{series_ticker}.json", {"markets": []})["markets"]
        return [m for m in ms if (status is None or m.get("status") == status) and (event_ticker is None or m.get("event_ticker") == event_ticker)]

    def historical_markets(self, series_ticker=None, event_ticker=None):
        return []

    def event(self, event_ticker):
        return self._load(f"event_{event_ticker}.json", {"event": {}})["event"]

    def candles(self, series_ticker, market_ticker, start_ts, end_ts, period_interval=1440):
        cs = self._load(f"candles_{market_ticker}.json", {"candlesticks": []})["candlesticks"]
        return [c for c in cs if start_ts <= c["end_period_ts"] <= end_ts]

    def open_events(self):
        return self._load("events_open.json", {"events": []})["events"]

    def all_series(self, category=None):
        return self._load("series_list.json", {"series": []})["series"]
