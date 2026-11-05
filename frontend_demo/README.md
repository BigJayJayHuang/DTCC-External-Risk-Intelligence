# Frontend demo data (not published)

**DEMO ONLY — every headline, score and reading in this folder is invented.** These files were moved out of `docs/`, because everything under `docs/` is published on GitHub Pages.

- `sample_risk_output.json`: Jay's original layout sample.
- `make_demo_data.py`: generator for a larger simulated demo file. It writes `frontend_demo/demo_risk_output.json`, which is git-ignored.

To view a demo file locally, serve the repository root and point the page at it:

```
python3 -m http.server 8000
# open http://localhost:8000/docs/index.html?data=../frontend_demo/sample_risk_output.json
```

The published page reads only `docs/data/risk_output.json`. That file is built by `docs/data/export_risk_output.py` from the scoring v1.3-indicator outputs.
