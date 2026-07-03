import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 터치알림 import build_scenario


def test_build_scenario_uses_top4_supports_and_nearest_resistance():
    sr = {
        "supports": [100, 95, 90, 85, 80],  # 5개 중 상위 4개만 써야 함
        "nearest_resistance": 120,
    }
    scenario = build_scenario(sr)
    assert scenario["entries"] == [100, 95, 90, 85]
    assert scenario["target"] == 120


def test_build_scenario_handles_missing_levels():
    scenario = build_scenario({"supports": [], "nearest_resistance": None})
    assert scenario["entries"] == []
    assert scenario["target"] is None
