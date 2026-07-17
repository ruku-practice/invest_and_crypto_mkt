import importlib.util
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_market_data.py"
SPEC = importlib.util.spec_from_file_location("fetch_market_data", MODULE_PATH)
assert SPEC and SPEC.loader
market_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(market_data)


class FakeIndexValue:
    def __init__(self, value: str):
        self.value = value

    def date(self):
        return datetime.strptime(self.value, "%Y-%m-%d").date()


class FakeSeries:
    def __init__(self, values, dates):
        self._values = values
        self.index = [FakeIndexValue(value) for value in dates]

    def dropna(self):
        return self

    def tolist(self):
        return self._values


class FakeHistory(dict):
    pass


class FetchMarketDataTests(unittest.TestCase):
    def test_yfinance_series_returns_actual_market_date(self):
        history = FakeHistory(
            Close=FakeSeries([100.0, 102.0], ["2026-07-15", "2026-07-16"])
        )
        ticker = unittest.mock.Mock()
        ticker.history.return_value = history

        with patch.object(market_data.yf, "Ticker", return_value=ticker):
            price, change, status, price_date = market_data.fetch_yfinance_series("^DJI")

        self.assertEqual(price, 102.0)
        self.assertAlmostEqual(change, 2.0)
        self.assertEqual(status, "ok")
        self.assertEqual(price_date, "2026-07-16")

    def test_normalize_history_does_not_duplicate_close_on_run_date(self):
        history = {
            "items": [{
                "id": "dow",
                "name": "NYダウ",
                "category": "index",
                "currency": "USD",
                "points": [
                    {"date": "2026/07/15", "value": 100.0},
                    {"date": "2026/07/16", "value": 102.0},
                ],
            }]
        }
        current = {
            "dow": {
                "id": "dow",
                "name": "NYダウ",
                "category": "index",
                "currency": "USD",
                "price": 102.0,
                "price_date": "2026/07/16",
                "status": "ok",
            }
        }

        normalized = market_data.normalize_history(history, current)
        points = normalized["items"][0]["points"]

        self.assertEqual([point["date"] for point in points], ["2026/07/15", "2026/07/16"])
        self.assertAlmostEqual(points[-1]["change_from_prev_pct"], 2.0)

    def test_merge_history_removes_old_closed_day_duplicates(self):
        existing = {
            "items": [
                {
                    "id": "dow",
                    "points": [
                        {"date": "2026/07/02", "value": 100.0, "fetched_at": "06:00"},
                        {"date": "2026/07/03", "value": 100.0, "fetched_at": "06:00"},
                    ],
                },
                {
                    "id": "gcho",
                    "points": [{"date": "2026/07/02", "value": 0.001}],
                },
            ]
        }
        rebuilt = {
            "items": [
                {"id": "dow", "points": [{"date": "2026/07/02", "value": 100.0}]},
                {"id": "gcho", "points": [{"date": "2026/07/03", "value": 0.002}]},
            ]
        }

        merged = market_data.merge_history(existing, rebuilt)
        by_id = {item["id"]: item for item in merged["items"]}

        self.assertEqual(
            by_id["dow"]["points"],
            [{"date": "2026/07/02", "value": 100.0, "fetched_at": "06:00"}],
        )
        self.assertEqual(
            [point["date"] for point in by_id["gcho"]["points"]],
            ["2026/07/02", "2026/07/03"],
        )


if __name__ == "__main__":
    unittest.main()
