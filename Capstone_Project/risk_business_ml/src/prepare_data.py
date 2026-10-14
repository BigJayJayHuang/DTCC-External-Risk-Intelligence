"""Build traceable quarterly business and risk data from original public sources."""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = pd.Timestamp("2026-10-05")
PERFORMANCE = ROOT.parent / "public_performance_data" / "2026-10-05"
METRICS = {
    "revenue_usd": r"Total revenues",
    "expenses_usd": r"Total expenses",
    "operating_income_usd": r"Total operating income(?: \((?:expense|loss)\))?",
    "net_income_usd": r"Net income(?: \(loss\))?",
}
SERIES = {
    "VIXCLS": ("Market volatility", "daily", "index points", "CBOE via FRED"),
    "DGS10": ("10-year US Treasury yield", "daily", "percent", "Federal Reserve Board via FRED"),
    "DGS2": ("2-year US Treasury yield", "daily", "percent", "Federal Reserve Board via FRED"),
    "SOFR": ("Secured Overnight Financing Rate", "daily", "percent", "Federal Reserve Bank of New York via FRED"),
    "EFFR": ("Effective Federal Funds Rate", "daily", "percent", "Federal Reserve Bank of New York via FRED"),
    "NFCICREDIT": ("Chicago Fed credit conditions subindex", "weekly", "index points", "Federal Reserve Bank of Chicago via FRED"),
}


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_setup():
    """Keep the exact inputs used in this analysis in the portable project."""
    raw = ROOT / "raw" / "business_documents"
    manifest_file = raw / "source_manifest.json"
    if PERFORMANCE.exists():
        manifest = json.loads((PERFORMANCE / "source_manifest.json").read_text())
        raw.mkdir(parents=True, exist_ok=True)
        selected = [d for d in manifest["documents"] if (
            d["actual_entity"] in {"FICC", "NSCC", "DTC"} and d["document_kind"] == "financial_statements"
        ) or (d["actual_format"] == "xlsx" and d["document_kind"] == "public_quantitative_disclosure")
            or d["file"] in {"quantitative_disclosures/DTCC_PQD_2024_Q4.pdf",
                              "quantitative_disclosures/DTCC_PQD_2021_Q3.pdf",
                              "quantitative_disclosures/DTCC_PQD_2022_Q3.pdf"}]
        for d in selected:
            dest = raw / d["file"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(PERFORMANCE / d["file"], dest)
            assert sha(dest) == d["sha256"], d["file"]
        write_json(manifest_file, {"documents": selected, "original_summary": manifest["summary"]})
    else:
        manifest = json.loads(manifest_file.read_text())
    return raw, json.loads(manifest_file.read_text())["documents"]


def numeric_row(text, pattern):
    line = next((l.strip() for l in text.splitlines() if re.match(r"\s*" + pattern + r"\s+", l)), None)
    if line is None:
        raise ValueError(f"Missing income row {pattern}")
    tail = re.sub(r"^" + pattern, "", line).strip()
    tokens = re.findall(r"\(?-?\d[\d,]*(?:\.\d+)?\)?|[—–]", tail)
    values = []
    for t in tokens:
        if t in {"—", "–"}:
            values.append(0.0)
        else:
            values.append((-1 if t.startswith("(") else 1) * float(t.strip("()").replace(",", "")) * 1000)
    return line, values


def business_financials(raw, documents):
    records, evidence, errors = [], [], []
    for d in documents:
        if d["document_kind"] != "financial_statements":
            continue
        reader = PdfReader(raw / d["file"])
        found = None
        for p, page in enumerate(reader.pages[:8], 1):
            text = page.extract_text()
            if "Total revenues" in text and "Total expenses" in text and "Net income" in text:
                found = (p, text)
                break
        if found is None:
            errors.append({"file": d["file"], "error": "Income statement not found"})
            continue
        page, text = found
        header = text.split("REVENUES")[0]
        assert "In thousands" in header, (d["file"], header)
        annual = "Annual" in d["file"]
        year, quarter = d["reporting_year"], d["reporting_quarter"]
        expected = 2 if annual or quarter == 1 else 4
        header_years = re.findall(r"\b(?:19|20)\d{2}\b", header)
        assert [int(v) for v in header_years[-expected:]] == [year, year - 1] * (expected // 2), (d["file"], header)
        if annual:
            layout = [(year, 12, "ytd"), (year - 1, 12, "ytd")]
        elif quarter == 1:
            layout = [(year, 3, "quarter"), (year - 1, 3, "quarter")]
        else:
            clean_header = " ".join(header.lower().split())
            assert clean_header.find("three months") < clean_header.find("six months" if quarter == 2 else "nine" if quarter == 3 else "years ended"), header
            layout = [(year, 3, "quarter"), (year - 1, 3, "quarter"), (year, quarter * 3, "ytd"), (year - 1, quarter * 3, "ytd")]
        source_date = next((r.get("listed_date") for r in d["source_listing_records"] if r.get("listing_matches_document")), None)
        common = {"entity": d["actual_entity"], "source_file": d["file"], "source_page": page,
                  "source_url": d["source_urls"][0], "source_sha256": d["sha256"],
                  "source_report_year": year, "source_report_quarter": quarter,
                  "audited_annual": annual, "portal_listed_date": source_date,
                  "release_date_verified": False}
        evidence.append(dict(common, income_statement_text=text))
        for metric, pattern in METRICS.items():
            line, values = numeric_row(text, pattern)
            assert len(values) == expected, (d["file"], line, values)
            for (data_year, months, kind), value in zip(layout, values):
                end_quarter = 4 if annual else quarter
                base = dict(common, metric=metric, year=data_year, end_quarter=end_quarter, months=months,
                            kind=kind, value=value, units="USD", original_units="USD thousands", raw_row=line,
                            comparative=data_year != year)
                records.append(base)
                if quarter == 1 and not annual:
                    records.append(dict(base, kind="ytd"))
    assert not errors, errors
    extracted = pd.DataFrame(records)
    extracted.to_csv(ROOT / "data/financial_observations.csv", index=False)
    write_json(ROOT / "data/financial_page_evidence.json", evidence)

    # Retrospective dataset: audited annual values take precedence for annual totals;
    # original-period quarterly values take precedence over later comparatives.
    keys = ["entity", "metric", "year", "end_quarter", "kind"]
    selected, conflicts = {}, []
    for key, group in extracted.groupby(keys, sort=True):
        ordered = group.sort_values(["audited_annual", "comparative", "source_report_year", "source_report_quarter"],
                                    ascending=[False, True, True, True])
        chosen = ordered.iloc[0].to_dict()
        selected[key] = chosen
        if group.value.max() - group.value.min() > 1000:
            conflicts.append({"key": key, "chosen": chosen, "alternatives": group.to_dict("records")})

    quarter_rows, reconciliations = [], []
    for entity in sorted(extracted.entity.unique()):
        for year in range(2019, 2027):
            for q in range(1, 5):
                if year == 2026 and q > 2:
                    continue
                for metric in METRICS:
                    key = (entity, metric, year, q, "quarter")
                    direct = selected.get(key)
                    derivations = []
                    a = selected.get((entity, metric, year, q, "ytd"))
                    b = selected.get((entity, metric, year, q - 1, "ytd")) if q > 1 else None
                    if q > 1 and a and b:
                        derivations.append((a["value"] - b["value"], [a, b], "YTD(q) - YTD(q-1)"))
                    if q == 1 and not direct:
                        a = selected.get((entity, metric, year, 2, "ytd"))
                        b = selected.get((entity, metric, year, 2, "quarter"))
                        if a and b:
                            derivations.append((a["value"] - b["value"], [a, b], "six-month YTD - Q2"))
                    if direct:
                        for v, parts, formula in derivations:
                            reconciliations.append({"entity": entity, "year": year, "quarter": q, "metric": metric,
                                                    "direct": direct["value"], "derived": v, "difference_usd": direct["value"] - v,
                                                    "formula": formula, "sources": [p["source_file"] for p in parts]})
                        value, sources, formula = direct["value"], [direct], "reported three-month value"
                        derived = False
                    elif derivations:
                        value, sources, formula = derivations[0]
                        derived = True
                    else:
                        continue
                    quarter_rows.append({"entity": entity, "quarter": str(pd.Period(f"{year}Q{q}", freq="Q")),
                                         "metric": metric, "value_usd": value, "derived": derived, "formula": formula,
                                         "source_files": " | ".join(s["source_file"] for s in sources),
                                         "source_pages": " | ".join(str(s["source_page"]) for s in sources),
                                         "source_urls": " | ".join(s["source_url"] for s in sources),
                                         "source_portal_dates": " | ".join(str(s["portal_listed_date"]) for s in sources),
                                         "point_in_time_vintage": False})
    detail = pd.DataFrame(quarter_rows)
    detail.to_csv(ROOT / "data/business_metric_provenance.csv", index=False)
    recon = pd.DataFrame(reconciliations)
    recon.to_csv(ROOT / "data/financial_reconciliations.csv", index=False)
    write_json(ROOT / "data/financial_conflicts.json", conflicts)
    wide = detail.pivot(index=["entity", "quarter"], columns="metric", values="value_usd").reset_index()
    wide.columns.name = None
    wide["operating_margin_pct"] = 100 * wide.operating_income_usd / wide.revenue_usd
    wide["net_margin_pct"] = 100 * wide.net_income_usd / wide.revenue_usd
    # Quarterly statements and audited totals should obey this exact accounting identity.
    residual = wide.revenue_usd - wide.expenses_usd - wide.operating_income_usd
    assert residual.abs().max() <= 1000, wide.loc[residual.abs() > 1000].to_dict("records")
    wide.to_csv(ROOT / "data/business_quarterly_financials.csv", index=False)
    return wide, {"financial_reports": len(evidence), "income_rows": len(extracted),
                  "business_quarter_rows": len(wide), "duplicate_value_conflicts": len(conflicts),
                  "derived_metric_values": int(detail.derived.sum()),
                  "quarter_reconciliations": len(recon),
                  "max_reconciliation_error_usd": float(recon.difference_usd.abs().max())}


def prepare_pqd(raw, documents):
    rows = []
    for d in documents:
        if d["actual_format"] != "xlsx":
            continue
        wb = load_workbook(raw / d["file"], data_only=True, read_only=True)
        sheet = wb["DTCC_DataFile_23"]
        content = list(sheet.values)
        header = list(content[0])
        assert "23.1.1" in header and "ReportLevelIdentifier" in header, (d["file"], header)
        for n, row in enumerate(content[1:], 2):
            r = dict(zip(header, row))
            division = str(r.get("ReportLevelIdentifier", "")).split("/")[-1]
            if division not in {"GSD", "MBSD", "NSCC"}:
                continue
            description = str(r.get("Description", ""))
            kind = "OTC" if "OTC" in description else "ETD" if "ETD" in description else description
            quarter = f"{d['reporting_year']}Q{d['reporting_quarter']}"
            assert str(pd.Timestamp(r["ReportDate"]).to_period("Q")) == quarter, (d["file"], r["ReportDate"])
            # Preserve NSCC template categories separately; do not sum uncertain scopes.
            for ref, name, units in [("23.1.1", "daily_sides", "sides per day"), ("23.1.2", "daily_notional_usd", "USD per day")]:
                v = pd.to_numeric(str(r.get(ref, "")).replace(",", ""), errors="coerce")
                if not np.isfinite(v):
                    continue
                rows.append({"quarter": quarter, "entity": "FICC" if division in {"GSD", "MBSD"} else "NSCC",
                             "division": division, "template_category": kind,
                             "metric": name, "value": v, "units": units,
                             "eligible_for_model": division in {"GSD", "MBSD"} and kind == "OTC",
                             "precision": "original XLSX numeric value",
                             "source_file": d["file"], "source_sheet": sheet.title, "source_row": n,
                             "source_reference": ref, "source_url": d["source_urls"][0]})
        wb.close()
    # Recover the missing XLSX quarter from the actual PDF table. PDF notionals
    # are rounded USD millions; this precision is retained in provenance.
    d = next(d for d in documents if d["file"] == "quantitative_disclosures/DTCC_PQD_2024_Q4.pdf")
    reader = PdfReader(raw / d["file"])
    for page_number, page in enumerate(reader.pages, 1):
        text = page.extract_text()
        if "23.1.1.1" not in text or "23.1.2.1" not in text:
            continue
        for start_ref, end_ref, name, label, multiplier, units in [
            ("23.1.1.1", "23.1.1.2", "daily_sides", "Quarterly", 1, "sides per day"),
            ("23.1.2.1", "23.1.2.2", "daily_notional_usd", "USD $MM", 1_000_000, "USD per day")]:
            section = text.split(start_ref, 1)[1].split(end_ref, 1)[0]
            numeric_section = section.split(label, 1)[1]
            values = [float(s.replace(",", "")) for s in re.findall(r"\b\d[\d,]*\b", numeric_section)[:3]]
            assert len(values) == 3
            for div, value in zip(["GSD", "MBSD", "NSCC"], values):
                rows.append({"quarter": "2024Q4", "entity": "FICC" if div != "NSCC" else "NSCC", "division": div,
                             "template_category": "OTC", "metric": name, "value": value * multiplier, "units": units,
                             "eligible_for_model": div in {"GSD", "MBSD"},
                             "precision": "PDF rounded to whole sides or USD millions",
                             "source_file": d["file"], "source_sheet": f"PDF page {page_number}", "source_row": None,
                             "source_reference": start_ref, "source_url": d["source_urls"][0]})
        write_json(ROOT / "data/pqd_pdf_page_evidence.json", {"source_file": d["file"], "page": page_number, "text": text})
        break
    else:
        raise ValueError("2024Q4 PDF activity table not found")
    operations = pd.DataFrame(rows)
    issues = []
    for quarter, behavior in [("2021Q3", "PDF confirms original XLSX notional values were in USD millions"),
                              ("2022Q3", "Both formats contain inconsistent notional magnitudes; cannot confirm intended unit")]:
        source_name = f"quantitative_disclosures/DTCC_PQD_{quarter[:4]}_Q{quarter[-1]}.pdf"
        doc = next(d for d in documents if d["file"] == source_name)
        reader = PdfReader(raw / source_name)
        for page_number, page in enumerate(reader.pages, 1):
            text = " ".join(page.extract_text().split())
            if "23.1.2" not in text:
                continue
            pdf_values_match = re.search(r"OTC USD\s+\$MM\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", text)
            assert pdf_values_match, (source_name, text[:1000])
            pdf_values = [float(v.replace(",", "")) * 1_000_000 for v in pdf_values_match.groups()]
            write_json(ROOT / f"data/pqd_{quarter}_unit_evidence.json", {"source_file": source_name, "source_page": page_number,
                                                                         "source_url": doc["source_urls"][0], "text": text,
                                                                         "unit_interpretation": behavior})
            for division, pdf_value in zip(["GSD", "MBSD"], pdf_values[:2]):
                mask = (operations.quarter == quarter) & (operations.division == division) & (operations.metric == "daily_notional_usd")
                assert mask.sum() == 1
                i = operations.index[mask][0]
                old = float(operations.loc[i, "value"])
                operations.loc[i, "original_xlsx_value"] = old
                operations.loc[i, "quality_issue"] = behavior
                if quarter == "2021Q3":
                    assert abs(old * 1_000_000 - pdf_value) <= 1_000_000, (division, old, pdf_value)
                    operations.loc[i, "value"] = pdf_value
                    operations.loc[i, "precision"] = "Normalized USD millions, verified against corresponding PDF"
                    operations.loc[i, "corroborating_source_file"] = source_name
                else:
                    operations.loc[i, "eligible_for_model"] = False
                issues.append({"quarter": quarter, "division": division, "metric": "daily_notional_usd",
                               "original_xlsx_value": old, "pdf_value_in_usd": pdf_value,
                               "action": "unit normalized from PDF evidence" if quarter == "2021Q3" else "excluded; no invented replacement",
                               "explanation": behavior, "source_file": source_name, "source_page": page_number})
            break
        else:
            raise ValueError(f"Unit corroboration page not found: {source_name}")
    write_json(ROOT / "data/pqd_source_quality_issues.json", issues)
    assert len(operations) > 0, "No usable PQD operation rows extracted"
    assert not operations.duplicated(["quarter", "division", "template_category", "metric"]).any()
    operations.to_csv(ROOT / "data/business_quarterly_operations.csv", index=False)
    return {"pqd_xlsx_reports": sum(d["actual_format"] == "xlsx" for d in documents),
            "operations_rows": len(operations), "operations_model_excluded_scope": "NSCC OTC/ETD scope not aggregated",
            "operations_missing_quarters": ["2022Q3 GSD/MBSD daily notionals excluded: unresolved source units"],
            "pqd_pdf_recovered_quarter": "2024Q4; rounded original PDF figures",
            "nscc_scope_note": "OTC/Exchange explanatory notes change over history; kept separate and excluded from operational modeling"}


def risk_series():
    source_rows, long_rows = [], []
    for sid, (name, frequency, units, provider) in SERIES.items():
        path = ROOT / f"raw/risk_series/{sid}.csv"
        df = pd.read_csv(path)
        assert list(df.columns) == ["observation_date", sid]
        df["date"] = pd.to_datetime(df.observation_date)
        df["value"] = pd.to_numeric(df[sid], errors="coerce")
        assert not df.date.duplicated().any() and df.date.max() <= CUTOFF
        source_rows.append({"series": sid, "name": name, "provider": provider, "frequency": frequency, "units": units,
                            "definition_url": f"https://fred.stlouisfed.org/series/{sid}",
                            "download_url": f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=2018-01-01&coed=2026-10-05",
                            "raw_file": str(path.relative_to(ROOT)), "sha256": sha(path),
                            "collected_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                            "observations": len(df), "missing_observations": int(df.value.isna().sum()),
                            "first_date": str(df.date.min().date()), "last_date": str(df.date.max().date()),
                            "vintage": "Retrieved current vintage; NFCI history may be revised"})
        df["series"], df["units"] = sid, units
        long_rows.append(df[["series", "date", "value", "units"]])
    long = pd.concat(long_rows, ignore_index=True)
    long.to_csv(ROOT / "data/risk_observations.csv", index=False)
    daily = long.pivot(index="date", columns="series", values="value").sort_index()
    q = daily.groupby(daily.index.to_period("Q")).mean()
    q.columns = [f"{c.lower()}_mean" for c in q.columns]
    counts = daily.groupby(daily.index.to_period("Q")).count()
    for c in counts:
        q[f"{c.lower()}_observations"] = counts[c]
    yield10 = daily.DGS10.dropna()
    end10 = yield10.groupby(yield10.index.to_period("Q")).last()
    q["rate_change_pp"] = end10.diff()
    q["vix_change_log_pct"] = 100 * np.log(q.vixcls_mean / q.vixcls_mean.shift(1))
    q["vix_change_pct"] = 100 * (q.vixcls_mean / q.vixcls_mean.shift(1) - 1)
    q["credit_change_index"] = q.nfcicredit_mean.diff()
    # Identical-date rate observations; no forward filling either series.
    basis = 100 * (daily.SOFR - daily.EFFR).dropna()
    q["funding_basis_max_bps"] = basis.groupby(basis.index.to_period("Q")).max()
    q["yield_curve_mean_pp"] = q.dgs10_mean - q.dgs2_mean
    # Never include the partial collection quarter in a historical quarterly analysis.
    q = q.loc[q.index < CUTOFF.to_period("Q")]
    q.index.name = "quarter"
    write_json(ROOT / "raw/risk_sources_manifest.json", source_rows)
    return q, source_rows


def official_news():
    records, coverage = [], []
    pattern = re.compile(r'<a[^>]+href=["\x27]([^"\x27]*/pressreleases/([a-z]+)(\d{8})[a-z]*\.htm)["\x27][^>]*>(.*?)</a>', re.I | re.S)
    for year in range(2019, 2027):
        path = ROOT / f"raw/official_news/fed_{year}.html"
        text = path.read_text(errors="replace")
        accepted, mismatches = 0, []
        for match in pattern.finditer(text):
            url, category, datecode, raw_title = match.groups()
            url = urljoin("https://www.federalreserve.gov", url)
            if url.endswith(".htm") is False:
                continue
            dates = re.findall(r"<time[^>]*>\s*(\d{1,2}/\d{1,2}/\d{4})\s*</time>", text[max(0, match.start()-500):match.start()])
            posted = pd.Timestamp(dates[-1]) if dates else None
            url_date = pd.to_datetime(datecode, format="%Y%m%d")
            if posted is None or posted != url_date or posted.year != year:
                mismatches.append({"url": url, "display_date": str(posted), "url_date": str(url_date)})
                continue
            if posted > CUTOFF:
                continue
            title = " ".join(html.unescape(re.sub("<[^>]+>", " ", raw_title)).split())
            records.append({"document_id": hashlib.sha256(url.encode()).hexdigest()[:24],
                            "source_id": "fed_press_archive", "source_name": "Board of Governors of the Federal Reserve System",
                            "url": url, "title": title, "published_date": str(posted.date()),
                            "date_precision": "day", "source_category": category.lower(),
                            "text_scope": "official_archive_headline_only", "raw_file": str(path.relative_to(ROOT)),
                            "collected_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                            "review_status": "unreviewed", "ai_generated": False,
                            "severity": None, "business_impact_verified": False})
            accepted += 1
        assert accepted > 25 and not mismatches, (year, accepted, mismatches[:5])
        coverage.append({"year": year, "accepted_headlines": accepted, "date_mismatches": len(mismatches),
                         "raw_file": str(path.relative_to(ROOT)), "sha256": sha(path),
                         "source_url": f"https://www.federalreserve.gov/newsevents/pressreleases/{year}-press.htm",
                         "coverage": "Year archive fetched and parsed; validated displayed dates, not a guarantee of every historical revision"})
    news = pd.DataFrame(records).drop_duplicates("url")
    news.to_csv(ROOT / "data/fed_historical_headlines.csv", index=False)
    news["quarter"] = pd.to_datetime(news.published_date).dt.to_period("Q")
    quarters = pd.period_range("2019Q1", "2026Q3", freq="Q")
    counts = news.groupby(["quarter", "source_category"]).size().unstack(fill_value=0).reindex(quarters, fill_value=0)
    result = pd.DataFrame(index=quarters)
    result["fed_regulatory_announcements"] = counts.get("bcreg", 0) + counts.get("enforcement", 0)
    result["fed_monetary_announcements"] = counts.get("monetary", 0)
    result["fed_total_announcements"] = counts.sum(axis=1)
    result.index.name = "quarter"
    write_json(ROOT / "raw/news_archive_manifest.json", coverage)
    seed_original = ROOT.parent / "public_news_prototype/output/latest_documents.jsonl"
    seed_path = ROOT / "raw/official_news/previous_75_documents.jsonl"
    if seed_original.exists():
        shutil.copy2(seed_original, seed_path)
    seed = [json.loads(l) for l in seed_path.read_text().splitlines() if l.strip()]
    # Historical archive counts use one source and one date definition. The recent
    # multi-agency seed remains evidence, never zero-filled into uncovered history.
    merged = {r["url"]: dict(r) for r in records}
    for s in seed:
        if s["url"] in merged:
            merged[s["url"]]["previous_feed_document"] = s
        else:
            merged[s["url"]] = dict(s, business_impact_verified=False)
    (ROOT / "data/all_news_evidence.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged.values()))
    return result, {"historical_fed_headlines": len(news), "previous_feed_documents": len(seed),
                    "all_unique_news_documents": len(merged), "seed_date_start": min(s["published_at_utc"] for s in seed),
                    "seed_date_end": max(s["published_at_utc"] for s in seed)}


def main():
    (ROOT / "data").mkdir(exist_ok=True)
    raw, docs = source_setup()
    business, business_quality = business_financials(raw, docs)
    operation_quality = prepare_pqd(raw, docs)
    risks, sources = risk_series()
    counts, news_quality = official_news()
    risks = risks.join(counts, how="left")
    risks.to_csv(ROOT / "data/risk_quarterly.csv")
    business["quarter_end"] = pd.PeriodIndex(business.quarter, freq="Q").end_time.date.astype(str)
    business.to_csv(ROOT / "data/business_quarterly_financials.csv", index=False)
    quality = {"prepared_at_utc": datetime.now(timezone.utc).isoformat(), "collection_cutoff_date": "2026-10-05",
               **business_quality, **operation_quality, **news_quality,
               "risk_series": len(sources), "risk_observations": sum(s["observations"] for s in sources),
               "financial_coverage": business.groupby("entity").agg(quarters=("quarter", "count"), first_quarter=("quarter", "min"), last_quarter=("quarter", "max")).reset_index().to_dict("records"),
               "not_modeled": ["ECS as a separately reported financial segment", "Remaining eight kickoff business lines",
                               "Cyber / operational / third-party / data-management incident severity", "DTCC-specific event impact"],
               "limits": ["Small independent quarterly sample", "Current-vintage retrospective inputs",
                          "Fed announcement counts measure communication, not risk severity",
                          "NSCC and DTC are legal entities with activities outside ECS",
                          "PQD 15.2 financial fields are annual, excluded as quarterly targets",
                          "PQD 17.3 incident figures are rolling 12 months, excluded as quarter-specific labels"]}
    write_json(ROOT / "data/data_quality_summary.json", quality)
    print(json.dumps(quality, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
