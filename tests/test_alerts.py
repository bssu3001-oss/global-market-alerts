import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from lib.alerts import check_alerts


def make_scenario(entries=(13090, 12964, 12781, 12660), target=13258):
    return {"entries": list(entries), "target": target}


class TestCheckAlerts(unittest.TestCase):
    def test_no_trigger_when_price_between_levels(self):
        quote = {"price": 13200, "change_pct": -0.5}
        triggered, state = check_alerts(quote, make_scenario(), {}, "2026-07-03")
        self.assertEqual(triggered, [])
        self.assertEqual(state, {"date": "2026-07-03", "fired": []})

    def test_support_touch_triggers_once(self):
        quote = {"price": 13000, "change_pct": -1.5}
        triggered, state = check_alerts(quote, make_scenario(), {}, "2026-07-03")
        keys = [k for k, _, _ in triggered]
        self.assertEqual(keys, ["support_0"])
        self.assertIn("1차 지지선", triggered[0][2])
        self.assertIn("support_0", state["fired"])

    def test_multiple_support_levels_touch_together(self):
        quote = {"price": 12900, "change_pct": -2.8}
        triggered, state = check_alerts(quote, make_scenario(), {}, "2026-07-03")
        keys = [k for k, _, _ in triggered]
        self.assertEqual(keys, ["support_0", "support_1"])

    def test_resistance_touch_triggers_sell_alert(self):
        quote = {"price": 13300, "change_pct": 1.2}
        triggered, state = check_alerts(quote, make_scenario(), {}, "2026-07-03")
        keys = [k for k, _, _ in triggered]
        self.assertEqual(keys, ["resistance"])
        self.assertIn("익절/매도", triggered[0][2])

    def test_same_day_duplicate_is_suppressed(self):
        quote = {"price": 13000, "change_pct": -1.5}
        _, state = check_alerts(quote, make_scenario(), {}, "2026-07-03")
        triggered_again, state2 = check_alerts(quote, make_scenario(), state, "2026-07-03")
        self.assertEqual(triggered_again, [])
        self.assertEqual(state2["fired"], state["fired"])

    def test_new_day_resets_and_refires(self):
        quote = {"price": 13000, "change_pct": -1.5}
        _, state = check_alerts(quote, make_scenario(), {}, "2026-07-03")
        triggered_next_day, state2 = check_alerts(quote, make_scenario(), state, "2026-07-04")
        keys = [k for k, _, _ in triggered_next_day]
        self.assertEqual(keys, ["support_0"])
        self.assertEqual(state2["date"], "2026-07-04")

    def test_no_price_returns_empty(self):
        triggered, state = check_alerts({}, make_scenario(), {"date": "x", "fired": ["a"]}, "2026-07-03")
        self.assertEqual(triggered, [])
        self.assertEqual(state, {"date": "x", "fired": ["a"]})


if __name__ == "__main__":
    unittest.main()
