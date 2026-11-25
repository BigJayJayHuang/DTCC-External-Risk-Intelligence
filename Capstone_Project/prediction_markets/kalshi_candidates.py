#!/usr/bin/env python3
"""Weekly Kalshi candidate list: one row per binary market that could matter to DTCC risk cards.

Output (snapshot_date = the Monday of the week):
  Capstone_Project/data/kalshi/<snapshot_date>/kalshi_candidates.csv   one row per market, mapping columns left blank
  Capstone_Project/data/kalshi/<snapshot_date>/raw/                    raw API JSON (events + candlesticks), for audit
  Capstone_Project/data/kalshi/<snapshot_date>/run_log.json            calls, counts, categories seen, price source
Public market-data endpoints only (no key): GET /events (nested markets) and market candlesticks.

Rules (config/candidates.json):
  - open markets closing within 18 months of the snapshot
  - allowed categories; Politics only for government-operation keywords; Crypto only for stablecoin/market-structure/
    regulator markets, never price levels; combo/parlay markets (KXMVE...) dropped
  - keyword match on market or event title, whole words (so "rate" does not match "corporate", "SEC" not "second")
  - prob_now = mid of the yes bid/ask (else last price) when run on or before the snapshot date; when run later it is the
    daily candle close on the snapshot date instead (prob_source says which)
  - prob_7d_ago = daily candle close 7 days earlier (blank if the market is newer); volume_7d = sum of the last 7 daily candles
All-or-nothing: the files are written to a temp folder and swapped in only if every API call succeeded. On failure the
previous snapshot stays and the error goes to Capstone_Project/data/kalshi/_errors/. Mapping columns already filled in
an existing file for the same week are kept on re-run (matched by market_ticker).

Usage (repo root, normal terminal):
  python3 Capstone_Project/prediction_markets/kalshi_candidates.py --snapshot-date 2026-11-30
  python3 Capstone_Project/prediction_markets/kalshi_candidates.py --snapshot-date 2026-11-30 --offline   # simulated data
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from kalshi_client import KalshiClient, to_float  # noqa: E402

OUT_ROOT = HERE.parent / "data" / "kalshi"
CONFIG = HERE / "config" / "candidates.json"
DAY = 86400

MAPPING = ["risk_family", "risk_subfamily", "business_lines", "related_card_ids", "placement", "why_it_matters", "approved"]
COLUMNS = (["snapshot_utc", "event_ticker", "series_ticker", "market_ticker", "event_title", "market_title", "category", "kalshi_url",
            "yes_bid", "yes_ask", "last_price", "prob_now", "prob_7d_ago", "change_7d_pts", "prob_source",
            "volume_24h", "volume_7d", "open_interest", "liquidity_ok",
            "open_time", "close_time", "expected_settlement_date", "status",
            "rules_short", "matched_keywords"] + MAPPING)
OPEN_STATUSES = {"open", "active"}


# ---------- selection (pure, unit-tested) ----------
def _kw_regex(words, case_sensitive):
    if not words:
        return None
    alts = "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alts})(?![A-Za-z0-9])", 0 if case_sensitive else re.IGNORECASE)


class Selector:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        cs = set(cfg.get("case_sensitive_keywords", []))
        def pair(words):
            return (_kw_regex([w for w in words if w in cs], True), _kw_regex([w for w in words if w not in cs], False))
        self.all_kw, self.pol_kw, self.cry_kw = pair(cfg["keywords"]), pair(cfg["politics_keywords"]), pair(cfg["crypto_keywords"])
        self.coins = _kw_regex(cfg.get("crypto_coins", []), False)
        self.price_words = re.compile(r"(?<![A-Za-z])(price|above|below|reach|hit|high|low)(?![A-Za-z])|\$\s?\d", re.IGNORECASE)

    @staticmethod
    def _find(pair, text):
        out = []
        for rx in pair:
            if rx:
                out += [m.group(0) for m in rx.finditer(text)]
        seen, res = set(), []
        for w in out:
            k = re.sub(r"\s+", " ", w).lower()
            if k not in seen:
                seen.add(k); res.append(re.sub(r"\s+", " ", w))
        return res

    def check(self, event: dict, market: dict, snapshot: date) -> tuple[bool, str, list]:
        """Return (keep, reason, matched_keywords)."""
        cfg = self.cfg
        tick = market.get("ticker", "") or ""
        ev_tick = event.get("event_ticker", "") or ""
        if any(tick.startswith(p) or ev_tick.startswith(p) for p in cfg.get("exclude_ticker_prefixes", [])):
            return False, "combo/parlay market", []
        if (market.get("status") or "").lower() not in OPEN_STATUSES:
            return False, "not open", []
        cat = event.get("category") or ""
        if cat not in cfg["categories"]:
            return False, f"category {cat or '(none)'}", []
        close = parse_ts(market.get("close_time"))
        horizon = datetime.combine(snapshot, datetime.min.time(), timezone.utc) + timedelta(days=round(cfg["horizon_months"] * 30.44))
        if close is None or close > horizon:
            return False, "closes after horizon", []
        text = " | ".join(x for x in (event.get("title"), event.get("sub_title"), market.get("title"), market.get("yes_sub_title")) if x)
        if cat in cfg.get("crypto_categories", []):
            if self.coins and self.coins.search(text) and self.price_words.search(text):
                return False, "crypto price level", []
            kws = self._find(self.cry_kw, text)
            return (bool(kws), "crypto: regulation keyword" if kws else "crypto: no regulation keyword", kws)
        pair = self.pol_kw if cat in cfg.get("politics_categories", []) else self.all_kw
        kws = self._find(pair, text)
        return (bool(kws), "keyword" if kws else "no keyword", kws)


# ---------- helpers ----------
def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def iso_min(s):
    d = parse_ts(s)
    return d.strftime("%Y-%m-%dT%H:%MZ") if d else ""


def r4(x):
    return "" if x is None else round(x, 4)


def candle_close(c):
    v = to_float((c.get("price") or {}).get("close_dollars"))
    if v is None:
        b = to_float((c.get("yes_bid") or {}).get("close_dollars"))
        a = to_float((c.get("yes_ask") or {}).get("close_dollars"))
        if b is not None and a is not None and a >= b:
            v = (a + b) / 2
    return v


def candle_volume(c):
    return to_float(c.get("volume_fp"), to_float(c.get("volume"), 0.0)) or 0.0


def last_close_before(candles, ts):
    best = None
    for c in candles:
        if c.get("end_period_ts", 0) <= ts and candle_close(c) is not None:
            if best is None or c["end_period_ts"] > best["end_period_ts"]:
                best = c
    return (candle_close(best), best) if best else (None, None)


def kalshi_url(series):
    return f"https://kalshi.com/markets/{series.lower()}" if series else ""


def short_rules(text, n):
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


# ---------- build ----------
def build_rows(client, cfg, snapshot: date, now: datetime, raw_dir: Path | None, log: dict, max_markets=None):
    sel = Selector(cfg)
    events = client.open_events()
    log["calls"] += 1
    if raw_dir:
        (raw_dir / "events.json").write_text(json.dumps({"events": events}, indent=1), encoding="utf-8")
    snap_end = int(datetime.combine(snapshot + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp())  # end of snapshot day, UTC
    historical = now.date() > snapshot
    log["mode"] = "candle_close (run after the snapshot date)" if historical else "live_quote"
    if now.date() < snapshot:
        log["warnings"].append(f"run on {now.date()} before the snapshot date {snapshot}: prices are as of the run time")
    snap_utc = (datetime.combine(snapshot, datetime.min.time(), timezone.utc) + timedelta(hours=21)) if historical else now
    rows, cats, reasons = [], {}, {}
    for ev in events:
        cats[ev.get("category") or "(none)"] = cats.get(ev.get("category") or "(none)", 0) + 1
        for m in ev.get("markets") or []:
            keep, why, kws = sel.check(ev, m, snapshot)
            reasons[why] = reasons.get(why, 0) + 1
            if not keep:
                continue
            if max_markets and len(rows) >= max_markets:
                log["warnings"].append(f"stopped at --max-markets {max_markets}")
                break
            series = ev.get("series_ticker") or m.get("series_ticker") or (m.get("event_ticker", "").split("-")[0])
            candles = client.candles(series, m["ticker"], snap_end - 10 * DAY, snap_end, 1440)
            log["calls"] += 1
            if raw_dir:
                (raw_dir / "candles").mkdir(exist_ok=True)
                (raw_dir / "candles" / f"{m['ticker']}.json").write_text(json.dumps({"candlesticks": candles}), encoding="utf-8")
            bid, ask, last = to_float(m.get("yes_bid_dollars")), to_float(m.get("yes_ask_dollars")), to_float(m.get("last_price_dollars"))
            if historical:
                p_now, c_now = last_close_before(candles, snap_end)
                src = "candle_close" if p_now is not None else ""
                vol24 = candle_volume(c_now) if c_now else None
                oi = to_float((c_now or {}).get("open_interest_fp"), to_float(m.get("open_interest_fp")))
            else:
                if bid is not None and ask is not None and ask > 0 and ask >= bid:
                    p_now, src = (bid + ask) / 2, "live_quote"
                elif last:
                    p_now, src = last, "last_price"
                else:
                    p_now, src = None, ""
                vol24, oi = to_float(m.get("volume_24h_fp")), to_float(m.get("open_interest_fp"))
            opened = parse_ts(m.get("open_time"))
            wk_ts = snap_end - 7 * DAY
            p_wk = None if (opened and opened.timestamp() > wk_ts) else last_close_before(candles, wk_ts)[0]
            vol7 = sum(candle_volume(c) for c in candles if snap_end - 7 * DAY < c.get("end_period_ts", 0) <= snap_end)
            lq = cfg["liquidity"]
            liq = "Y" if ((oi or 0) >= lq["min_open_interest"] or vol7 >= lq["min_volume_7d"]) else "N"
            rows.append({
                "snapshot_utc": snap_utc.strftime("%Y-%m-%dT%H:%MZ"), "event_ticker": ev.get("event_ticker", ""), "series_ticker": series,
                "market_ticker": m["ticker"], "event_title": ev.get("title", ""), "market_title": m.get("yes_sub_title") or m.get("title", ""),
                "category": ev.get("category", ""), "kalshi_url": kalshi_url(series),
                "yes_bid": r4(bid), "yes_ask": r4(ask), "last_price": r4(last), "prob_now": r4(p_now), "prob_7d_ago": r4(p_wk),
                "change_7d_pts": "" if p_now is None or p_wk is None else round((p_now - p_wk) * 100, 1), "prob_source": src,
                "volume_24h": "" if vol24 is None else round(vol24), "volume_7d": round(vol7), "open_interest": "" if oi is None else round(oi),
                "liquidity_ok": liq, "open_time": iso_min(m.get("open_time")), "close_time": iso_min(m.get("close_time")),
                "expected_settlement_date": (iso_min(m.get("expected_expiration_time") or m.get("latest_expiration_time")) or "")[:10],
                "status": m.get("status", ""), "rules_short": short_rules(m.get("rules_primary"), cfg.get("rules_chars", 200)),
                "matched_keywords": "|".join(kws), **{k: "" for k in MAPPING}})
        else:
            continue
        break
    log["categories_seen"] = dict(sorted(cats.items(), key=lambda x: -x[1]))
    log["filter_counts"] = dict(sorted(reasons.items(), key=lambda x: -x[1]))
    rows.sort(key=lambda r: (r["category"], r["event_ticker"], r["market_ticker"]))
    return rows


def keep_mapping(rows, old_csv: Path):
    """Re-running a week keeps whatever was already typed into the mapping columns."""
    if not old_csv.exists():
        return 0
    with old_csv.open(encoding="utf-8-sig", newline="") as f:
        old = {r["market_ticker"]: r for r in csv.DictReader(f)}
    n = 0
    for r in rows:
        o = old.get(r["market_ticker"])
        if o and any(o.get(k) for k in MAPPING):
            for k in MAPPING:
                r[k] = o.get(k, "")
            n += 1
    return n


def write_snapshot(rows, out_dir: Path, tmp: Path, log: dict):
    rows_kept = keep_mapping(rows, out_dir / "kalshi_candidates.csv")
    log["mapping_rows_kept"] = rows_kept
    with (tmp / "kalshi_candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader(); w.writerows(rows)
    (tmp / "run_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    old = out_dir.with_name(out_dir.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if out_dir.exists():
        out_dir.rename(old)
    tmp.rename(out_dir)
    if old.exists():
        shutil.rmtree(old)


def run(snapshot: date, client, cfg, out_root: Path, now: datetime, max_markets=None, offline=False):
    out_dir = out_root / snapshot.isoformat()
    tmp = out_root / f".{snapshot.isoformat()}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "raw").mkdir(parents=True)
    log = {"snapshot_date": snapshot.isoformat(), "run_utc": now.isoformat(timespec="seconds"), "config_version": cfg.get("version"),
           "source": "Kalshi public market data" + (" (SIMULATED fixtures)" if offline else ""), "calls": 0, "warnings": []}
    try:
        rows = build_rows(client, cfg, snapshot, now, tmp / "raw", log, max_markets)
        log["rows"] = len(rows)
        log["liquidity_ok_rows"] = sum(r["liquidity_ok"] == "Y" for r in rows)
        write_snapshot(rows, out_dir, tmp, log)
        return out_dir, rows, log
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        err_dir = out_root / "_errors"
        err_dir.mkdir(parents=True, exist_ok=True)
        log.update(error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc())
        p = err_dir / f"{snapshot.isoformat()}_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
        p.write_text(json.dumps(log, indent=2), encoding="utf-8")
        raise SystemExit(f"Kalshi run failed ({e}). Previous snapshot left as is; details in {p}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot-date", required=True, type=date.fromisoformat, help="Monday of the week, YYYY-MM-DD")
    ap.add_argument("--offline", action="store_true", help="simulated fixtures, no network (writes under data/kalshi/_offline_demo)")
    ap.add_argument("--max-markets", type=int, help="cap rows for a quick test")
    ap.add_argument("--out-root", type=Path)
    ap.add_argument("--config", type=Path, default=CONFIG)
    a = ap.parse_args(argv)
    if a.snapshot_date.weekday() != 0:
        print(f"note: {a.snapshot_date} is not a Monday")
    cfg = json.loads(a.config.read_text())
    if a.offline:
        from fixture_client import FixtureClient
        client = FixtureClient(HERE / "fixtures" / "candidates")
        now = datetime.combine(a.snapshot_date, datetime.min.time(), timezone.utc) + timedelta(hours=21)
        root = a.out_root or OUT_ROOT / "_offline_demo"
    else:
        client, now, root = KalshiClient(), datetime.now(timezone.utc), a.out_root or OUT_ROOT
    out_dir, rows, log = run(a.snapshot_date, client, cfg, root, now, a.max_markets, a.offline)
    print(f"{len(rows)} markets ({log['liquidity_ok_rows']} pass liquidity), prices: {log['mode']}, {log['calls']} API calls")
    print(f"categories seen: {log['categories_seen']}")
    for w in log["warnings"]:
        print("warning:", w)
    print(f"-> {out_dir / 'kalshi_candidates.csv'}")


if __name__ == "__main__":
    main()
