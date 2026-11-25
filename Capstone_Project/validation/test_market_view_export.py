"""Export hook for the prediction-market box (docs/data/export_risk_output.py). Offline."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("export_risk_output", REPO / "docs" / "data" / "export_risk_output.py")
X = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(X)

VIEW = {"ok": True, "topic": "government_shutdown", "question": "Will there be a government shutdown?", "p_yes": 0.68,
        "p_no": 0.32, "agreement": "agrees", "factor": 1.09, "applied": False}


class MarketViewExport(unittest.TestCase):
    def test_display_only_by_default(self):
        it = X.attach_market_view({"shock": 3, "S_source": "event_manual"}, VIEW)
        self.assertFalse(it["market_view"]["applied"])
        self.assertNotIn("shock_adjusted", it)

    def test_applied_only_to_event_scored_cards(self):
        it = X.attach_market_view({"shock": 3, "S_source": "event_manual"}, VIEW, apply_factor=True)
        self.assertEqual((it["shock_adjusted"], it["market_view"]["applied"]), (3.3, True))
        it = X.attach_market_view({"shock": 3, "S_source": "market"}, VIEW, apply_factor=True)
        self.assertNotIn("shock_adjusted", it)
        it = X.attach_market_view({"shock": 5, "S_source": "market+event_manual"}, dict(VIEW, factor=1.25), apply_factor=True)
        self.assertEqual(it["shock_adjusted"], 5.0)                     # capped at 5
        self.assertEqual(it["shock"], 5)                                # the original shock is never overwritten

    def test_export_unchanged_without_views_and_box_with_views(self):
        with tempfile.TemporaryDirectory() as d:
            plain = X.build(X.WEEKS, market_views_dir=Path(d))
            self.assertFalse(any("market_view" in i for i in plain["items"]))
            card = next(i["card_id"] for i in plain["items"] if i["snapshot"] == "2026-11-02")
            (Path(d) / "market_views_2026-11-02.json").write_text(json.dumps({"cards": {card: VIEW}}))
            out = X.build(X.WEEKS, market_views_dir=Path(d))
            hit = [i for i in out["items"] if "market_view" in i]
            self.assertTrue(hit and all(i["card_id"] == card and i["snapshot"] == "2026-11-02" for i in hit))


if __name__ == "__main__":
    unittest.main()
