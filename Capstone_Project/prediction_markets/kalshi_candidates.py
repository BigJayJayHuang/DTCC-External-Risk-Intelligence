#!/usr/bin/env python3
"""Point-in-time Kalshi candidate list: what the market expected at the end of each dashboard week.

One file per week (week = Monday; snapshot = the end of that Sunday, US Eastern, i.e. 00:00 ET the next Monday):
  Capstone_Project/data/kalshi/<monday>/kalshi_candidates.csv   one row per binary market live at the snapshot
  Capstone_Project/data/kalshi/<monday>/raw/                    raw API JSON (events, closed markets, candlesticks)
  Capstone_Project/data/kalshi/<monday>/run_log.json            calls, categories seen, filter counts, price source
Public market-data endpoints only (no key).

Point-in-time rules (no look-ahead):
  - a market is included only if open_time <= as_of < close_time (it was live then); markets that have since closed or
    settled are fetched too (GET /markets status=closed/settled, then /historical/markets)
  - prob_as_of = daily candle close at the snapshot; prob_7d_before = close 7 days earlier; volume and open interest
    from the candles at that date. For a week that is not over yet, live quotes are used (prob_source = live_quote)
  - result / settled_at / outcome_note record what happened later; they are for the "expected vs happened" slide and are
    never shown on the main page
Selection (config/candidates.json): categories + whole-word keywords as before; Politics only for government keywords;
Crypto only for regulation; combo/parlay markets dropped. --subjects-from adds the news classifier's forward_subject
phrases for that week (prompt v1.7) so markets about a named subject (e.g. "Jensen Huang return as Nvidia CEO") are
included from any category except the deny list.
All-or-nothing: written to a temp folder and swapped in only if every API call succeeded; on failure the previous file
stays and the error goes to data/kalshi/_errors/. Mapping columns already filled are kept on re-run.

Usage (repo root, normal terminal):
  python3 Capstone_Project/prediction_markets/kalshi_candidates.py --week 2026-11-02 --week 2026-11-09 --week 2026-11-16
  python3 Capstone_Project/prediction_markets/kalshi_candidates.py --week 2026-11-09 --subjects-from <candidates.csv>
  python3 Capstone_Project/prediction_markets/kalshi_candidates.py --week 2026-11-09 --offline      # simulated data
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import traceback
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from kalshi_client import KalshiClient, to_float  # noqa: E402

OUT_ROOT = HERE.parent / "data" / "kalshi"
CONFIG = HERE / "config" / "candidates.json"
ET = ZoneInfo("America/New_York")
DAY = 86400
OFFLINE_NOW = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)   # fixtures are built around this date

MAPPING = ["risk_family", "risk_subfamily", "business_lines", "related_card_ids", "placement", "why_it_matters", "approved"]
COLUMNS = (["as_of_utc", "event_ticker", "series_ticker", "market_ticker", "event_title", "market_title", "category", "kalshi_url",
            "yes_bid", "yes_ask", "last_price", "prob_as_of", "prob_7d_before", "change_7d_pts", "prob_source",
            "volume_24h", "volume_7d", "open_interest", "liquidity_ok",
            "open_time", "close_time", "expected_settlement_date", "status", "rules_short", "matched_keywords",
            "result", "settled_at", "outcome_note"] + MAPPING)
OPEN_STATUSES = {"open", "active"}
STOP = {"the", "and", "for", "will", "with", "from", "that", "this", "into", "back", "by", "of", "to", "in", "on", "a", "an",
        "be", "is", "as", "at", "or", "its", "his", "her", "their", "than", "after", "before", "end", "who", "what", "when"}


def as_of_for(monday: date) -> datetime:
    """End of that week's Sunday, US Eastern (= 00:00 ET the next Monday), in UTC."""
    return datetime.combine(monday + timedelta(days=7), time(0), ET).astimezone(timezone.utc)


def content_words(text: str | None) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z0-9&$.%-]+", text or "") if len(w) >= 3 and w.lower().strip(".") not in STOP]


def word_hits(words, text) -> int:
    low = " " + re.sub(r"[^a-z0-9&$%]+", " ", (text or "").lower()) + " "
    return sum(f" {re.sub(r'[^a-z0-9&$%]+', ' ', w.lower()).strip()} " in low for w in words)


# ---------- selection (pure, unit-tested) ----------
def _kw_regex(words, case_sensitive):
    if not words:
        return None
    alts = "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alts})(?![A-Za-z0-9])", 0 if case_sensitive else re.IGNORECASE)


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


class Selector:
    def __init__(self, cfg: dict, subjects=None):
        self.cfg = cfg
        cs = set(cfg.get("case_sensitive_keywords", []))
        def pair(words):
            return (_kw_regex([w for w in words if w in cs], True), _kw_regex([w for w in words if w not in cs], False))
        self.all_kw, self.pol_kw, self.cry_kw = pair(cfg["keywords"]), pair(cfg["politics_keywords"]), pair(cfg["crypto_keywords"])
        self.loose = _kw_regex(cfg["keywords"], False)
        self.coins = _kw_regex(cfg.get("crypto_coins", []), False)
        self.price_words = re.compile(r"(?<![A-Za-z])(price|above|below|reach|hit|high|low)(?![A-Za-z])|\$\s?\d", re.IGNORECASE)
        self.subjects = [(s, content_words(s)) for s in (subjects or []) if content_words(s)]

    @staticmethod
    def _find(pair, text):
        res, seen = [], set()
        for rx in pair:
            for m in (rx.finditer(text) if rx else []):
                w = re.sub(r"\s+", " ", m.group(0))
                if w.lower() not in seen:
                    seen.add(w.lower()); res.append(w)
        return res

    def subject_hits(self, text):
        need = self.cfg.get("subject_min_words", 2)
        return [s for s, ws in self.subjects if word_hits(ws, text) >= min(need, len(ws))]

    def maybe(self, market: dict) -> bool:
        """Cheap pre-filter on a bare market (before its event is fetched)."""
        text = " ".join(str(market.get(k) or "") for k in ("title", "yes_sub_title", "subtitle", "event_ticker"))
        return bool((self.loose and self.loose.search(text)) or self.subject_hits(text))

    def check(self, event: dict, market: dict, as_of: datetime, live: bool) -> tuple[bool, str, list]:
        cfg = self.cfg
        tick, ev_tick = market.get("ticker", "") or "", event.get("event_ticker", "") or ""
        if any(tick.startswith(p) or ev_tick.startswith(p) for p in cfg.get("exclude_ticker_prefixes", [])):
            return False, "combo/parlay market", []
        if live and (market.get("status") or "").lower() not in OPEN_STATUSES:
            return False, "not open", []
        opened, close = parse_ts(market.get("open_time")), parse_ts(market.get("close_time"))
        if opened and opened > as_of:
            return False, "opened after the snapshot", []
        if close is None or close <= as_of:
            return False, "closed before the snapshot", []
        if close > as_of + timedelta(days=round(cfg["horizon_months"] * 30.44)):
            return False, "closes after horizon", []
        cat = event.get("category") or ""
        if cat in cfg.get("deny_categories", []):
            return False, f"category {cat}", []
        text = " | ".join(x for x in (event.get("title"), event.get("sub_title"), market.get("title"), market.get("yes_sub_title")) if x)
        subj = ["subject: " + s for s in self.subject_hits(text)]
        if cat not in cfg["categories"]:
            return (True, "news subject", subj) if subj else (False, f"category {cat or '(none)'}", [])
        if cat in cfg.get("crypto_categories", []):
            if self.coins and self.coins.search(text) and self.price_words.search(text):
                return False, "crypto price level", []
            kws = self._find(self.cry_kw, text) + subj
            return (bool(kws), "crypto: regulation keyword" if kws else "crypto: no regulation keyword", kws)
        kws = self._find(self.pol_kw if cat in cfg.get("politics_categories", []) else self.all_kw, text) + subj
        return (bool(kws), "keyword" if kws else "no keyword", kws)


# ---------- prices ----------
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
        if c.get("end_period_ts", 0) <= ts and candle_close(c) is not None and (best is None or c["end_period_ts"] > best["end_period_ts"]):
            best = c
    return (candle_close(best), best) if best else (None, None)


def iso_min(s):
    d = parse_ts(s)
    return d.strftime("%Y-%m-%dT%H:%MZ") if d else ""


def r4(x):
    return "" if x is None else round(x, 4)


def short_rules(text, n):
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def outcome(m: dict, p_as_of, as_of: datetime):
    st = (m.get("status") or "").lower()
    res = (m.get("result") or "").lower()
    if st in OPEN_STATUSES or st in ("", "unopened", "initialized"):
        return "open", "", ""
    if res in ("yes", "no"):
        when = iso_min(m.get("settlement_ts") or m.get("expiration_time") or m.get("close_time"))
        note = f"Settled {res.upper()} on {when[:10]}"
        if p_as_of is not None:
            note += f"; market gave {round(p_as_of * 100)}% YES as of {as_of.astimezone(ET).date()}"
        return res, when, note
    return "pending", "", f"Closed ({st}), result not posted yet"


# ---------- build ----------
def build_rows(client, cfg, monday: date, now: datetime, raw_dir: Path | None, log: dict, subjects=None, max_markets=None):
    sel = Selector(cfg, subjects)
    as_of = as_of_for(monday)
    live = now < as_of
    snap = now if live else as_of
    log.update(as_of_utc=snap.isoformat(timespec="minutes"),
               mode="live_quote (week not over yet)" if live else "candle_close at the end of the week (point in time)")
    events = client.open_events(); log["calls"] += 1
    pairs = [(ev, m) for ev in events for m in (ev.get("markets") or [])]
    if raw_dir:
        (raw_dir / "events_open.json").write_text(json.dumps({"events": events}, indent=1), encoding="utf-8")
    if not live:   # markets that were live at the snapshot but have closed or settled since
        closed = client.markets_closed_since(int(as_of.timestamp())); log["calls"] += 1
        if raw_dir:
            (raw_dir / "markets_closed_since.json").write_text(json.dumps({"markets": closed}, indent=1), encoding="utf-8")
        known, cache = {m.get("ticker") for _, m in pairs}, {}
        for m in closed:
            if m.get("ticker") in known or not sel.maybe(m):
                continue
            et = m.get("event_ticker", "")
            if et not in cache:
                cache[et] = client.event(et); log["calls"] += 1
            pairs.append((cache[et], m)); known.add(m.get("ticker"))
        if raw_dir and cache:
            (raw_dir / "events_of_closed_markets.json").write_text(json.dumps(cache, indent=1), encoding="utf-8")
    snap_ts = int(snap.timestamp())
    rows, cats, reasons = [], {}, {}
    for ev, m in pairs:
        cats[ev.get("category") or "(none)"] = cats.get(ev.get("category") or "(none)", 0) + 1
        keep, why, kws = sel.check(ev, m, snap, live)
        reasons[why] = reasons.get(why, 0) + 1
        if not keep:
            continue
        if max_markets and len(rows) >= max_markets:
            log["warnings"].append(f"stopped at --max-markets {max_markets}")
            break
        series = ev.get("series_ticker") or m.get("series_ticker") or m.get("event_ticker", "").split("-")[0]
        candles = client.candles(series, m["ticker"], snap_ts - 10 * DAY, snap_ts, 1440); log["calls"] += 1
        if raw_dir:
            (raw_dir / "candles").mkdir(exist_ok=True)
            (raw_dir / "candles" / f"{m['ticker']}.json").write_text(json.dumps({"candlesticks": candles}), encoding="utf-8")
        bid, ask, last = to_float(m.get("yes_bid_dollars")), to_float(m.get("yes_ask_dollars")), to_float(m.get("last_price_dollars"))
        if live:
            if bid is not None and ask is not None and ask > 0 and ask >= bid:
                p, src = (bid + ask) / 2, "live_quote"
            elif last:
                p, src = last, "last_price"
            else:
                p, src = None, ""
            vol24, oi = to_float(m.get("volume_24h_fp")), to_float(m.get("open_interest_fp"))
        else:
            p, c = last_close_before(candles, snap_ts)
            src = "candle_close" if p is not None else ""
            vol24 = candle_volume(c) if c else None
            oi = to_float((c or {}).get("open_interest_fp"))
            bid = ask = last = None          # today's quotes would be look-ahead for a past week
        opened = parse_ts(m.get("open_time"))
        wk = snap_ts - 7 * DAY
        p7 = None if (opened and opened.timestamp() > wk) else last_close_before(candles, wk)[0]
        vol7 = sum(candle_volume(c) for c in candles if wk < c.get("end_period_ts", 0) <= snap_ts)
        lq = cfg["liquidity"]
        res, settled_at, note = outcome(m, p, snap) if not live else ("open", "", "")
        rows.append({
            "as_of_utc": snap.strftime("%Y-%m-%dT%H:%MZ"), "event_ticker": ev.get("event_ticker") or m.get("event_ticker", ""),
            "series_ticker": series, "market_ticker": m["ticker"], "event_title": ev.get("title", ""),
            "market_title": m.get("yes_sub_title") or m.get("title", ""), "category": ev.get("category", ""),
            "kalshi_url": f"https://kalshi.com/markets/{series.lower()}" if series else "",
            "yes_bid": r4(bid), "yes_ask": r4(ask), "last_price": r4(last), "prob_as_of": r4(p), "prob_7d_before": r4(p7),
            "change_7d_pts": "" if p is None or p7 is None else round((p - p7) * 100, 1), "prob_source": src,
            "volume_24h": "" if vol24 is None else round(vol24), "volume_7d": round(vol7), "open_interest": "" if oi is None else round(oi),
            "liquidity_ok": "Y" if ((oi or 0) >= lq["min_open_interest"] or vol7 >= lq["min_volume_7d"]) else "N",
            "open_time": iso_min(m.get("open_time")), "close_time": iso_min(m.get("close_time")),
            "expected_settlement_date": (iso_min(m.get("expected_expiration_time") or m.get("latest_expiration_time")) or "")[:10],
            "status": "open" if not live else m.get("status", ""),
            "rules_short": short_rules(m.get("rules_primary"), cfg.get("rules_chars", 200)),
            "matched_keywords": "|".join(kws), "result": res, "settled_at": settled_at, "outcome_note": note,
            **{k: "" for k in MAPPING}})
    log["categories_seen"] = dict(sorted(cats.items(), key=lambda x: -x[1]))
    log["filter_counts"] = dict(sorted(reasons.items(), key=lambda x: -x[1]))
    rows.sort(key=lambda r: (r["category"], r["event_ticker"], r["market_ticker"]))
    return rows


def keep_mapping(rows, old_csv: Path):
    if not old_csv.exists():
        return 0
    with old_csv.open(encoding="utf-8-sig", newline="") as f:
        old = {r["market_ticker"]: r for r in csv.DictReader(f)}
    n = 0
    for r in rows:
        o = old.get(r["market_ticker"])
        if o and any(o.get(k) for k in MAPPING):
            r.update({k: o.get(k, "") for k in MAPPING}); n += 1
    return n


def read_rows(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def run(monday: date, client, cfg, out_root: Path, now: datetime, max_markets=None, offline=False, subjects=None):
    out_dir, tmp = out_root / monday.isoformat(), out_root / f".{monday.isoformat()}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "raw").mkdir(parents=True)
    log = {"week": monday.isoformat(), "run_utc": now.isoformat(timespec="seconds"), "config_version": cfg.get("version"),
           "source": "Kalshi public market data" + (" (SIMULATED fixtures)" if offline else ""), "calls": 0, "warnings": [],
           "subjects": list(subjects or [])}
    try:
        rows = build_rows(client, cfg, monday, now, tmp / "raw", log, subjects, max_markets)
        log.update(rows=len(rows), liquidity_ok_rows=sum(r["liquidity_ok"] == "Y" for r in rows),
                   mapping_rows_kept=keep_mapping(rows, out_dir / "kalshi_candidates.csv"))
        with (tmp / "kalshi_candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
        (tmp / "run_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
        old = out_dir.with_name(out_dir.name + ".old")
        if old.exists():
            shutil.rmtree(old)
        if out_dir.exists():
            out_dir.rename(old)
        tmp.rename(out_dir)
        shutil.rmtree(old, ignore_errors=True)
        return out_dir, rows, log
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        (out_root / "_errors").mkdir(parents=True, exist_ok=True)
        log.update(error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc())
        p = out_root / "_errors" / f"{monday.isoformat()}_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
        p.write_text(json.dumps(log, indent=2), encoding="utf-8")
        raise SystemExit(f"Kalshi run failed ({e}). Previous snapshot left as is; details in {p}")


def subjects_from(paths) -> list[str]:
    out = []
    for p in paths or []:
        for r in read_rows(p):
            s = (r.get("forward_subject") or "").strip()
            if s and (r.get("forward_topic") or "none") != "none" and s not in out:
                out.append(s)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", action="append", required=True, type=date.fromisoformat, help="Monday of a dashboard week (repeatable)")
    ap.add_argument("--subjects-from", nargs="+", type=Path, help="news classifier candidates CSV(s) with forward_subject (prompt v1.7)")
    ap.add_argument("--offline", action="store_true", help="simulated fixtures, no network (writes under data/kalshi/_offline_demo)")
    ap.add_argument("--max-markets", type=int)
    ap.add_argument("--out-root", type=Path)
    ap.add_argument("--config", type=Path, default=CONFIG)
    a = ap.parse_args(argv)
    cfg = json.loads(a.config.read_text())
    if a.offline:
        from fixture_client import FixtureClient
        client, now, root = FixtureClient(HERE / "fixtures" / "candidates"), OFFLINE_NOW, a.out_root or OUT_ROOT / "_offline_demo"
    else:
        client, now, root = KalshiClient(), datetime.now(timezone.utc), a.out_root or OUT_ROOT
    subjects = subjects_from(a.subjects_from)
    for w in a.week:
        if w.weekday() != 0:
            print(f"note: {w} is not a Monday")
        out_dir, rows, log = run(w, client, cfg, root, now, a.max_markets, a.offline, subjects)
        print(f"week {w} (as of {log['as_of_utc']}): {len(rows)} markets, {log['liquidity_ok_rows']} pass liquidity, "
              f"{log['mode']}, {log['calls']} API calls -> {out_dir / 'kalshi_candidates.csv'}")
        for x in log["warnings"]:
            print("  warning:", x)
    print("categories seen (last week):", log["categories_seen"])


if __name__ == "__main__":
    main()
