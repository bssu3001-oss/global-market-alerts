import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.support_resistance import support_resistance


def make_candles():
    """전체적으로 100~130 사이를 오가는 합성 캔들 250개. 저점 100 근처, 고점 130 근처에서 반복 반등."""
    candles = []
    base_date = 20260101
    for i in range(250):
        cycle = i % 20
        low = 100 + (5 if 8 <= cycle <= 12 else 0)
        high = low + 25
        close = (low + high) / 2
        candles.append({
            "date": f"day{i:04d}",
            "open": close, "high": high, "low": low, "close": close,
            "volume": 1000 + i,
        })
    # 마지막 캔들의 종가를 지지선(100대)과 저항선(130대) 사이 중간값으로 고정
    candles[-1]["close"] = 115
    return candles


def test_support_resistance_returns_expected_keys():
    sr = support_resistance(make_candles())
    for key in ("supports", "resistances", "nearest_support", "nearest_resistance",
                "strongest_support", "strongest_resistance"):
        assert key in sr


def test_supports_are_below_current_price():
    candles = make_candles()
    sr = support_resistance(candles)
    current = candles[-1]["close"]
    for s in sr["supports"]:
        assert s < current


def test_resistances_are_above_current_price():
    candles = make_candles()
    sr = support_resistance(candles)
    current = candles[-1]["close"]
    for r in sr["resistances"]:
        assert r > current
