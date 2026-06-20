#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
글로벌 증시 조건부 카톡 알림 — GitHub Actions 10분마다 실행
조건 충족 시에만 카톡 발송, 같은 조건 하루 1번만 발송
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

import yfinance as yf

KST = timezone(timedelta(hours=9))
STATE_FILE = os.path.join(os.path.dirname(__file__), "알림상태.json")
DASHBOARD_BASE = "https://bssu3001-oss.github.io"

COUNTRIES = {
    "india":     {"name": "인도",      "flag": "🇮🇳", "ticker": "^NSEI",  "label": "NIFTY 50",  "dashboard": f"{DASHBOARD_BASE}/india-market-dashboard/"},
    "vietnam":   {"name": "베트남",    "flag": "🇻🇳", "ticker": "VNM",    "label": "VN-Index",  "dashboard": f"{DASHBOARD_BASE}/vietnam-fund-dashboard/", "scale": 99.5744},
    "indonesia": {"name": "인도네시아","flag": "🇮🇩", "ticker": "^JKSE",  "label": "IDX",       "dashboard": f"{DASHBOARD_BASE}/indonesia-market-dashboard/"},
    "us":        {"name": "미국",      "flag": "🇺🇸", "ticker": "^GSPC",  "label": "S&P 500",   "dashboard": f"{DASHBOARD_BASE}/us-market-dashboard/"},
    "brazil":    {"name": "브라질",    "flag": "🇧🇷", "ticker": "^BVSP",  "label": "IBOVESPA",  "dashboard": f"{DASHBOARD_BASE}/brazil-market-dashboard/"},
}


# ── 상태 관리 ──

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def already_sent(state, key):
    today = datetime.now(KST).strftime("%Y-%m-%d")
    return key in state.get(today, [])

def mark_sent(state, key):
    today = datetime.now(KST).strftime("%Y-%m-%d")
    state.setdefault(today, [])
    if key not in state[today]:
        state[today].append(key)


# ── RSI 계산 ──

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains  = [d for d in deltas[-period:] if d > 0]
    losses = [-d for d in deltas[-period:] if d < 0]
    avg_g = sum(gains) / period if gains else 0
    avg_l = sum(losses) / period if losses else 0
    if avg_l == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_g / avg_l)), 1)


# ── 시장 데이터 수집 ──

def fetch_data(country_key):
    cfg = COUNTRIES[country_key]
    ticker_sym = cfg["ticker"]
    scale = cfg.get("scale", 1.0)

    t = yf.Ticker(ticker_sym)

    # 현재가 & 전일 대비 등락률
    try:
        fi = t.fast_info
        current = fi.last_price * scale
        prev = fi.previous_close * scale
        pct = (current - prev) / prev * 100
    except Exception:
        hist = t.history(period="5d", interval="1d")
        closes = [float(r["Close"]) for _, r in hist.iterrows()]
        current = closes[-1] * scale
        prev = closes[-2] * scale if len(closes) >= 2 else current
        pct = (current - prev) / prev * 100

    # 베트남: ^VNINDEX.VN 직접 시도
    if country_key == "vietnam":
        try:
            vn = yf.Ticker("^VNINDEX.VN")
            vn_price = vn.fast_info.last_price
            if vn_price and vn_price > 100:
                vn_prev = vn.fast_info.previous_close or prev / scale
                current = vn_price
                prev = vn_prev
                pct = (current - prev) / prev * 100
        except Exception:
            pass

    # RSI(14) - 일봉 60일치
    try:
        hist_d = t.history(period="60d", interval="1d")
        prices_d = [float(r["Close"]) * scale for _, r in hist_d.iterrows()]
        rsi = calc_rsi(prices_d)
    except Exception:
        rsi = 50.0

    # 52주 고점 대비 위치
    try:
        hist_y = t.history(period="1y", interval="1d")
        closes_y = [float(r["Close"]) * scale for _, r in hist_y.iterrows()]
        hi52 = max(closes_y)
        from_hi = (current - hi52) / hi52 * 100
    except Exception:
        from_hi = 0.0

    # 연속 하락일수 (일봉 기준)
    consec_down = 0
    try:
        closes_r = [float(r["Close"]) * scale for _, r in hist_d.iterrows()]
        for i in range(len(closes_r) - 1, 0, -1):
            if closes_r[i] < closes_r[i - 1]:
                consec_down += 1
            else:
                break
    except Exception:
        pass

    # 보조 지표
    india_vix = us_vix = None
    if country_key == "india":
        try:
            india_vix = round(yf.Ticker("^INDIAVIX").fast_info.last_price, 1)
        except Exception:
            pass
    try:
        us_vix = round(yf.Ticker("^VIX").fast_info.last_price, 1)
    except Exception:
        pass

    return {
        "current": round(current, 1),
        "pct": round(pct, 2),
        "rsi": rsi,
        "from_hi": round(from_hi, 1),
        "consec_down": consec_down,
        "india_vix": india_vix,
        "us_vix": us_vix,
    }


# ── 알림 조건 체크 ──

def check_conditions(country_key, data):
    alerts = []
    pct       = data["pct"]
    rsi       = data["rsi"]
    from_hi   = data["from_hi"]
    down      = data["consec_down"]
    us_vix    = data.get("us_vix")
    india_vix = data.get("india_vix")

    if rsi <= 35:
        alerts.append({"type": "매수_rsi",
            "msg": f"RSI {rsi} — 과매도 구간, 분할 매수 검토"})

    if pct <= -2.0:
        alerts.append({"type": "매수_급락",
            "msg": f"당일 {pct:.2f}% 급락 — 단기 저점 매수 기회"})

    if from_hi <= -15.0:
        alerts.append({"type": "매수_저점",
            "msg": f"52주 고점 대비 {from_hi:.1f}% 하락 — 조정 구간 진입"})

    if rsi >= 75:
        alerts.append({"type": "주의_rsi",
            "msg": f"RSI {rsi} — 과매수 구간, 차익실현 검토"})

    if pct >= 2.0:
        alerts.append({"type": "주의_급등",
            "msg": f"당일 +{pct:.2f}% 급등 — 단기 고점, 신규 진입 자제"})

    if down >= 3:
        alerts.append({"type": "주의_연속하락",
            "msg": f"{down}일 연속 하락 — 추세 하락 경고, 관망 권장"})

    if country_key == "india" and india_vix and india_vix >= 22:
        alerts.append({"type": "주의_vix",
            "msg": f"India VIX {india_vix} — 변동성 급등, 신규 매수 자제"})

    if country_key == "us" and us_vix and us_vix >= 28:
        alerts.append({"type": "주의_vix",
            "msg": f"미국 VIX {us_vix} — 공포 구간, 포지션 점검"})

    if country_key not in ("india", "us") and us_vix and us_vix >= 28:
        alerts.append({"type": "주의_vix",
            "msg": f"미국 VIX {us_vix} — 글로벌 공포, 신흥국 영향 주의"})

    return alerts


# ── 카카오 API ──

def kakao_get_access_token(rest_api_key, refresh_token, client_secret=None):
    params = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    if client_secret:
        params["client_secret"] = client_secret
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        "https://kauth.kakao.com/oauth/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"토큰 갱신 HTTP {e.code}: {body}")
    if "access_token" not in result:
        raise RuntimeError(f"토큰 갱신 실패: {result}")
    return result["access_token"]

def kakao_send(access_token, text, dashboard_url):
    template = json.dumps({
        "object_type": "text",
        "text": text[:1000],
        "link": {"web_url": dashboard_url, "mobile_web_url": dashboard_url},
        "button_title": "대시보드 열기",
    }, ensure_ascii=False)
    data = urllib.parse.urlencode({"template_object": template}).encode()
    req = urllib.request.Request(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        data=data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())
    if result.get("result_code") != 0:
        raise RuntimeError(f"메시지 전송 실패: {result}")
    print("✅ 카카오 전송 완료")


# ── 메인 ──

def main():
    rest_api_key  = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "").strip()
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "").strip() or None

    if not rest_api_key or not refresh_token:
        print("⚠️  KAKAO 환경변수 없음 — 알림 건너뜀")
        return

    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"[{now_kst}] 글로벌 증시 알림체크 시작")

    state = load_state()
    access_token = kakao_get_access_token(rest_api_key, refresh_token, client_secret)

    for country_key, cfg in COUNTRIES.items():
        flag = cfg["flag"]
        name = cfg["name"]
        label = cfg["label"]
        dashboard_url = cfg["dashboard"]

        print(f"\n{flag} {name} 체크 중...")
        try:
            data = fetch_data(country_key)
        except Exception as e:
            print(f"  데이터 수집 실패: {e}")
            continue

        print(f"  {label}: {data['current']:,.0f} ({data['pct']:+.2f}%) | RSI {data['rsi']} | 고점대비 {data['from_hi']:.1f}%")

        alerts = check_conditions(country_key, data)
        for alert in alerts:
            send_key = f"{country_key}_{alert['type']}"
            if already_sent(state, send_key):
                print(f"  ⏭ 오늘 이미 발송: {send_key}")
                continue

            msg = (
                f"{flag} [{name}] {'🟢 매수 신호!' if '매수' in alert['type'] else '⚠️ 주의'}\n"
                f"{label} {data['current']:,.0f} ({data['pct']:+.2f}%)\n"
                f"→ {alert['msg']}"
            )
            kakao_send(access_token, msg, dashboard_url)
            mark_sent(state, send_key)
            save_state(state)
            print(f"  → 발송: {send_key}")

        if not alerts:
            print("  조건 없음")

    cutoff = (datetime.now(KST) - timedelta(days=3)).strftime("%Y-%m-%d")
    for d in list(state.keys()):
        if d < cutoff:
            del state[d]
    save_state(state)
    print("\n완료")


if __name__ == "__main__":
    main()
