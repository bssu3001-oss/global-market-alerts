# -*- coding: utf-8 -*-
"""
5개 시장 지지선/저항선 도달 시 ntfy 푸시 알림.

기존 알림체크.py(하루 1회, 카톡 시황 다이제스트)와는 완전히 분리된 스크립트/워크플로우.
장중 자주(15분 간격) 돌면서 가격이 지지선에 닿으면 매수 알림, 저항선에 닿으면 매도 알림을
ntfy.sh로 보낸다. 카카오와 달리 토큰 회전이 없어 기존 다이제스트 발송에 영향을 주지 않는다.
"""

import os
import json
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from 알림체크 import MARKETS
from lib.support_resistance import support_resistance
from lib.alerts import check_alerts
from lib.ntfy import send_ntfy

STATE_FILE = "알림상태_터치.json"
KST = ZoneInfo("Asia/Seoul")

DASHBOARD_URLS = {
    "^NSEI": "https://bssu3001-oss.github.io/india-market-dashboard/",
    "VNM": "https://bssu3001-oss.github.io/vietnam-fund-dashboard/",
    "^JKSE": "https://bssu3001-oss.github.io/indonesia-market-dashboard/",
    "^GSPC": "https://bssu3001-oss.github.io/us-market-dashboard/",
    "^BVSP": "https://bssu3001-oss.github.io/brazil-market-dashboard/",
}


def fetch_ohlc(ticker):
    """일봉 OHLCV를 kodex-india와 동일한 candle 딕셔너리 리스트로 변환."""
    df = yf.download(ticker, period="2y", interval="1d", auto_adjust=False, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 60:
        return None
    candles = []
    for idx, row in df.iterrows():
        candles.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]) if "Volume" in row and pd.notna(row["Volume"]) else 0.0,
        })
    return candles


def build_scenario(sr):
    """터치 알림엔 지지선(entries)·저항선(target)만 필요 — evaluate()의 점수/평단 로직은 불필요."""
    supports = sr.get("supports") or []
    return {"entries": supports[:4], "target": sr.get("nearest_resistance")}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC 미설정 → 스킵")
        return

    today = dt.datetime.now(KST).date().isoformat()
    state = load_state()

    for ticker, cfg in MARKETS.items():
        try:
            candles = fetch_ohlc(ticker)
        except Exception as e:
            print(f"[{cfg['name']}] OHLC 조회 실패 → 스킵: {e}")
            continue
        if not candles:
            print(f"[{cfg['name']}] 데이터 부족 → 스킵")
            continue

        sr = support_resistance(candles)
        scenario = build_scenario(sr)

        price = candles[-1]["close"]
        prev_close = candles[-2]["close"] if len(candles) >= 2 else price
        change_pct = (price - prev_close) / prev_close * 100 if prev_close else None
        quote = {"price": price, "change_pct": change_pct}

        ticker_state = state.get(ticker, {})
        triggered, ticker_state = check_alerts(quote, scenario, ticker_state, today)
        state[ticker] = ticker_state

        for key, level, msg in triggered:
            full_msg = f"{cfg['flag']}[{cfg['name']}] {msg}"
            send_ntfy(topic, full_msg, click_url=DASHBOARD_URLS.get(ticker))

        print(f"[{cfg['name']}] 지지 {scenario['entries']} / 저항 {scenario['target']} "
              f"/ 신규알림 {[k for k, _, _ in triggered]}")

    save_state(state)


if __name__ == "__main__":
    main()
