import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 알림체크 import calc_rsi, check_conditions, already_sent, mark_sent


# ── RSI 계산 테스트 ──

def test_rsi_oversold():
    prices = [100 - i for i in range(15)]
    rsi = calc_rsi(prices)
    assert rsi < 30, f"과매도 RSI 예상, 실제: {rsi}"

def test_rsi_overbought():
    prices = [100 + i for i in range(15)]
    rsi = calc_rsi(prices)
    assert rsi > 70, f"과매수 RSI 예상, 실제: {rsi}"

def test_rsi_neutral():
    prices = [100, 102, 100, 102, 100, 102, 100, 102, 100, 102, 100, 102, 100, 102, 100]
    rsi = calc_rsi(prices)
    assert 40 < rsi < 60, f"중립 RSI 예상, 실제: {rsi}"


# ── 조건 체크 테스트 ──

def make_data(pct=0.0, rsi=50.0, from_hi=-5.0, consec_down=0, us_vix=None, india_vix=None):
    return {
        "current": 24000,
        "pct": pct,
        "rsi": rsi,
        "from_hi": from_hi,
        "consec_down": consec_down,
        "us_vix": us_vix,
        "india_vix": india_vix,
    }

def test_buy_rsi_oversold():
    data = make_data(rsi=33)
    alerts = check_conditions("india", data)
    types = [a["type"] for a in alerts]
    assert "매수_rsi" in types

def test_no_buy_rsi_normal():
    data = make_data(rsi=50)
    alerts = check_conditions("india", data)
    types = [a["type"] for a in alerts]
    assert "매수_rsi" not in types

def test_buy_급락():
    data = make_data(pct=-2.5)
    alerts = check_conditions("india", data)
    types = [a["type"] for a in alerts]
    assert "매수_급락" in types

def test_no_buy_소폭하락():
    data = make_data(pct=-1.0)
    alerts = check_conditions("india", data)
    types = [a["type"] for a in alerts]
    assert "매수_급락" not in types

def test_caution_급등():
    data = make_data(pct=2.5)
    alerts = check_conditions("india", data)
    types = [a["type"] for a in alerts]
    assert "주의_급등" in types

def test_caution_rsi_overbought():
    data = make_data(rsi=76)
    alerts = check_conditions("india", data)
    types = [a["type"] for a in alerts]
    assert "주의_rsi" in types

def test_caution_연속하락():
    data = make_data(consec_down=3)
    alerts = check_conditions("india", data)
    types = [a["type"] for a in alerts]
    assert "주의_연속하락" in types

def test_caution_from_hi():
    data = make_data(from_hi=-16)
    alerts = check_conditions("india", data)
    types = [a["type"] for a in alerts]
    assert "매수_저점" in types

def test_caution_us_vix():
    data = make_data(us_vix=30)
    alerts = check_conditions("us", data)
    types = [a["type"] for a in alerts]
    assert "주의_vix" in types

def test_caution_india_vix():
    data = make_data(india_vix=24)
    alerts = check_conditions("india", data)
    types = [a["type"] for a in alerts]
    assert "주의_vix" in types


# ── 중복 발송 방지 테스트 ──

def test_already_sent_false_initially():
    state = {}
    assert not already_sent(state, "india_매수_rsi")

def test_mark_and_already_sent():
    state = {}
    mark_sent(state, "india_매수_rsi")
    assert already_sent(state, "india_매수_rsi")

def test_different_keys_independent():
    state = {}
    mark_sent(state, "india_매수_rsi")
    assert not already_sent(state, "us_매수_rsi")
