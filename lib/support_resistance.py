"""kodex-india-dashboard(lib/indicators.py)의 support_resistance()를 그대로 포팅.
입력 형식만 동일하게 맞추면(list of {date,open,high,low,close,volume}) 검증된 로직을
그대로 재사용할 수 있어, 서로 다른 레포 간 계산 결과 불일치 리스크를 없앤다."""


def _sma_current(candles, period):
    if len(candles) < period:
        return None
    return round(sum(c["close"] for c in candles[-period:]) / period, 2)


def support_resistance(candles, lookback=60, res_lookback=250):
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    res_recent = candles[-res_lookback:] if len(candles) >= res_lookback else candles
    current = candles[-1]["close"]

    swing_lows = []
    for i in range(2, len(recent) - 2):
        l = recent[i]["low"]
        if l == min(c["low"] for c in recent[i - 2 : i + 3]):
            swing_lows.append(l)

    swing_highs = []
    for i in range(2, len(res_recent) - 2):
        h = res_recent[i]["high"]
        if h == max(c["high"] for c in res_recent[i - 2 : i + 3]):
            swing_highs.append(h)

    for p in (20, 60, 120):
        v = _sma_current(candles, p)
        if v:
            if v < current:
                swing_lows.append(v)
            else:
                swing_highs.append(v)

    def cluster(prices, threshold_pct=0.5):
        if not prices:
            return []
        prices = sorted(set(round(p, 0) for p in prices))
        clusters = [[prices[0]]]
        for p in prices[1:]:
            if abs(p - clusters[-1][0]) / clusters[-1][0] * 100 < threshold_pct:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        return [round(sum(c) / len(c), 0) for c in clusters]

    supports = sorted([p for p in cluster(swing_lows) if p < current], reverse=True)[:4]
    resistances = sorted([p for p in cluster(swing_highs) if p > current])[:5]

    nearest_support = supports[0] if supports else None
    nearest_resistance = resistances[0] if resistances else None

    ma_levels = [m for m in (_sma_current(candles, 60), _sma_current(candles, 120)) if m]
    test_window = candles[-120:] if len(candles) >= 120 else candles

    def _strength(level):
        band = level * 0.007
        touches = sum(1 for c in test_window if abs(c["low"] - level) <= band)
        confluence = sum(1 for m in ma_levels if abs(m - level) / level <= 0.012)
        return touches, confluence, touches + confluence * 3

    support_meta = []
    strongest_support = None
    best_score = -1
    for s in supports:
        t, conf, score = _strength(s)
        support_meta.append({"level": s, "touches": t, "confluence": conf, "score": score})
        if score > best_score:
            best_score = score
            strongest_support = s

    def _res_strength(level):
        band = level * 0.007
        touches = sum(1 for c in res_recent if abs(c["high"] - level) <= band)
        confluence = sum(1 for m in ma_levels if abs(m - level) / level <= 0.012)
        return touches, confluence, touches + confluence * 3

    resistance_meta = []
    strongest_resistance = None
    best_res_score = -1
    for r in resistances:
        t, conf, score = _res_strength(r)
        resistance_meta.append({"level": r, "touches": t, "confluence": conf, "score": score})
        if score > best_res_score:
            best_res_score = score
            strongest_resistance = r

    return {
        "supports": supports,
        "resistances": resistances,
        "support_meta": support_meta,
        "resistance_meta": resistance_meta,
        "strongest_support": strongest_support,
        "strongest_resistance": strongest_resistance,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "dist_to_support_pct": round((current - nearest_support) / current * 100, 2) if nearest_support else None,
        "dist_to_resistance_pct": round((nearest_resistance - current) / current * 100, 2) if nearest_resistance else None,
    }
