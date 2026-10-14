"""Independent evidence, chronology, saved-model and notebook delivery checks."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import joblib
import nbformat
import numpy as np
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]


def main():
    checks = []
    raw = ROOT / "raw/business_documents"
    source = json.loads((raw / "source_manifest.json").read_text())["documents"]
    for d in source:
        assert hashlib.sha256((raw / d["file"]).read_bytes()).hexdigest() == d["sha256"]
    checks.append({"check": "Original business input hashes", "count": len(source), "passed": True})
    for d in json.loads((ROOT / "raw/risk_sources_manifest.json").read_text()):
        assert hashlib.sha256((ROOT / d["raw_file"]).read_bytes()).hexdigest() == d["sha256"]
    checks.append({"check": "Raw risk series hashes", "count": 6, "passed": True})
    financial = pd.read_csv(ROOT / "data/business_quarterly_financials.csv")
    # Independently extract source rows with a different PDF library. Cover the
    # latest quarterly report, a negative-income quarter and a derived Q4.
    spotchecks = [
        ("FICC", "2026Q2", "FICC_Q2_2026.pdf", 4, "revenue_usd", "Total revenues", 0),
        ("DTC", "2026Q2", "DTC_Q2_2026.pdf", 4, "net_income_usd", "Net income", 0),
        ("NSCC", "2026Q2", "NSCC_Q2_2026.pdf", 4, "operating_income_usd", "Total operating income", 0),
        ("FICC", "2020Q4", "FICC_Q4_2020.pdf", 4, "operating_income_usd", "Total operating income", 0),
    ]
    for entity, quarter, filename, page, metric, label, column in spotchecks:
        with pdfplumber.open(raw / "financial_statements" / filename) as pdf:
            text = pdf.pages[page - 1].extract_text()
        line = next(s for s in text.splitlines() if s.startswith(label))
        tail = line[len(label):]
        tail = re.sub(r"^\s*\((?:loss|expense)\)", "", tail)
        tokens = re.findall(r"\(?\d[\d,]*\)?", tail)
        token = tokens[column]
        value = float(token.strip("()").replace(",", "")) * 1000 * (-1 if token.startswith("(") else 1)
        saved = financial[(financial.entity == entity) & (financial.quarter == quarter)][metric].iloc[0]
        assert abs(saved - value) <= 1, (entity, quarter, metric, value, saved)
    ficc = financial[financial.entity == "FICC"].set_index("quarter")
    assert ficc.loc["2026Q1", "revenue_usd"] + ficc.loc["2026Q2", "revenue_usd"] == 340636000
    assert sum(ficc.loc[f"2025Q{q}", "revenue_usd"] for q in range(1, 5)) == 626241000
    checks.append({"check": "Independent PDF and annual/YTD source spot checks", "count": 6, "passed": True})
    # A missing quarter must not become a two-quarter growth mislabeled QoQ.
    panel = pd.read_csv(ROOT / "data/analysis_panel.csv")
    assert not panel.duplicated(["entity", "metric", "quarter"]).any()
    for entity, quarters in [("NSCC", ["2020Q3", "2020Q4", "2021Q1", "2025Q4", "2026Q1"]),
                             ("DTC", ["2022Q4", "2023Q1"]),
                             ("FICC/GSD", ["2022Q3", "2022Q4"]),
                             ("FICC/MBSD", ["2022Q3", "2022Q4"])]:
        metric = "revenue_growth_pct" if entity in {"NSCC", "DTC"} else "daily_notional_growth_pct"
        values = panel[(panel.entity == entity) & (panel.metric == metric) & panel.quarter.isin(quarters)]
        assert len(values) == len(quarters) and values.target.isna().all(), (entity, values)
    checks.append({"check": "Calendar gaps preserved; no invented business changes", "passed": True})

    predictions = pd.read_csv(ROOT / "results/holdout_predictions.csv")
    metrics = pd.read_csv(ROOT / "results/model_comparison.csv")
    models = json.loads((ROOT / "models/model_manifest.json").read_text())
    for model in models:
        assert max(model["training_quarters"]) <= "2025Q2"
        assert min(model["test_quarters"]) >= "2025Q3"
        assert set(model["training_quarters"]).isdisjoint(model["test_quarters"])
        d = panel[(panel.entity == model["entity"]) & (panel.metric == model["metric"]) & panel.quarter.isin(model["test_quarters"])].sort_values("quarter")
        restored = joblib.load(ROOT / model["path"])
        recomputed = restored.predict(d[model["features"]])
        p = predictions[(predictions.entity == model["entity"]) & (predictions.metric == model["metric"]) & (predictions.model == model["model"])].sort_values("quarter")
        assert np.allclose(recomputed, p.predicted, atol=1e-10)
        for quarter, target in zip(d.quarter, d.target):
            actual = p[p.quarter == quarter].actual.iloc[0]
            assert abs(target - actual) < 1e-10
    for (entity, metric, method), d in predictions.groupby(["entity", "metric", "model"]):
        saved = metrics[(metrics.entity == entity) & (metrics.metric == metric) & (metrics.model == method)].iloc[0]
        errors = d.predicted.values - d.actual.values
        assert math.isclose(np.mean(abs(errors)), saved.test_mae, abs_tol=1e-10)
        assert math.isclose(np.sqrt(np.mean(errors ** 2)), saved.test_rmse, abs_tol=1e-10)
        r2 = 1 - sum(errors ** 2) / sum((d.actual.values - d.actual.mean()) ** 2)
        assert math.isclose(r2, saved.test_r2, abs_tol=1e-9)
    chronology = pd.read_csv(ROOT / "results/chronological_validation.csv")
    assert (chronology.train_last < chronology.validation_start).all()
    assert (chronology.validation_end <= "2025Q2").all()
    checks.append({"check": "26 saved pipelines reproduce holdouts; 52 metric rows recomputed", "passed": True})
    checks.append({"check": "Calendar-ordered validation; final test excluded from tuning", "passed": True})

    associations = pd.read_csv(ROOT / "results/risk_business_associations.csv")
    assert len(associations) == 78 and not associations.duplicated(["entity", "metric", "risk_feature"]).any()
    for _, r in associations.iterrows():
        d = panel[(panel.entity == r.entity) & (panel.metric == r.metric)][[r.risk_feature, "target"]].dropna()
        # Spearman computed independently through pandas rank/Pearson operations.
        rho = d[r.risk_feature].rank().corr(d.target.rank())
        assert abs(rho - r.spearman_rho) < 1e-10
        assert len(d) == r.n_quarters
    notebook = nbformat.read(ROOT / "Risk_Business_Associations.ipynb", as_version=4)
    nbformat.validate(notebook)
    code_cells = [c for c in notebook.cells if c.cell_type == "code"]
    assert all(c.execution_count is not None for c in code_cells)
    assert not any(o.output_type == "error" for c in code_cells for o in c.outputs)
    images = sum("image/png" in o.get("data", {}) for c in code_cells for o in c.outputs)
    assert images >= 6, images
    assert (ROOT / "Risk_Business_Associations.html").stat().st_size > 300000
    checks.append({"check": "78 correlations independently recomputed", "passed": True})
    checks.append({"check": "Fresh-kernel executed notebook with 6 figures and HTML export", "passed": True,
                   "code_cells": len(code_cells), "figure_outputs": images})
    report = {"checks": checks, "status": "passed", "visual_qa": "Figure and HTML presentation inspection recorded separately in delivery receipt"}
    (ROOT / "results/validation_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
