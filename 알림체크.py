# -*- coding: utf-8 -*-
"""
글로벌 증시 조건부 카톡 알림 — 펀드 holder 버전

설계 원칙
  1) 평일 1회(한국시간 아침) 실행 — 10분 폴링 아님
  2) 각 시장의 '확정된 일봉 종가'로만 신호 계산
  3) edge 트리거 + 쿨다운 → 같은 신호가 매일 반복 발송되지 않음
  4) 티커별 조회 실패는 스킵(전체 run 을 죽이지 않음)
  5) 펀드 주문 컷오프(기본 17:00 KST) 전에 검토할 수 있게 안내
"""

import os
import json
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import pandas as pd
import yfinance as yf

# ----------------------------------------------------------------------
# 설정 — 본인 펀드에 맞게 이 블록만 손보면 됩니다
# ----------------------------------------------------------------------
STATE_FILE = "알림상태.json"
COOLDOWN_DAYS = 5            # 같은 신호 재발송 최소 간격(일)
FUND_CUTOFF = "17:00"       # 펀드 주문 컷오프(한국시간). 투자설명서에서 확인 후 수정
DASHBOARD_URL = "https://bssu3001-oss.github.io"
KST = ZoneInfo("Asia/Seoul")

# holding=True : 현재 보유 중(매도/차익실현 신호도 받음)
# holding=False: 관심/진입 후보(매수·레짐 신호만 받음)
MARKETS = {
    "^NSEI":       {"name": "인도",       "flag": "🇮🇳", "index": "NIFTY 50",      "holding": True,  "vix": "^INDIAVIX", "vix_th": 22},
    "VNM":         {"name": "베트남",     "flag": "🇻🇳", "index": "VNM ETF",      "holding": False, "vix": None,        "vix_th": None},
    "^JKSE":       {"name": "인도네시아", "flag": "🇮🇩", "index": "IDX Composite", "holding": False, "vix": None,        "vix_th": None},
    "^GSPC":       {"name": "미국",       "flag": "🇺🇸", "index": "S&P 500",       "holding": False, "vix": "^VIX",      "vix_th": 28},
    "^BVSP":       {"name": "브라질",     "flag": "🇧🇷", "index": "IBOVESPA",      "holding": False, "vix": None,        "vix_th": None},
}

TAG = {"buy": "🟢", "sell": "🔴", "warn": "🟡"}


def daily_move_threshold(ticker):
    # 신흥국은 ±2% 변동이 흔해 노이즈가 큼 → 2.5%, 미국만 2%
    return 0.02 if ticker == "^GSPC" else 0.025


# ----------------------------------------------------------------------
# 지표
# ----------------------------------------------------------------------
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_close(ticker):
    """일봉 종가 시리즈 반환. 실패/부족 시 None."""
    df = yf.download(ticker, period="2y", interval="1d",
                     auto_adjust=False, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):          # 단일 티커도 멀티인덱스로 올 때가 있음
        df.columns = df.columns.get_level_values(0)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    return close if len(close) >= 60 else None


def fetch_last(ticker):
    """VIX 등 단일 값 조회용."""
    try:
        s = fetch_close(ticker)
        return None if s is None else float(s.iloc[-1])
    except Exception:
        return None


# ----------------------------------------------------------------------
# 신호 평가 — '현재 참인 조건'의 집합을 만든다
# ----------------------------------------------------------------------
def evaluate(ticker, cfg, close):
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    chg = (last - prev) / prev
    r = rsi(close).iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    ma120 = close.rolling(120).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1]
    ma200_prev = close.rolling(200).mean().iloc[-2]
    high_52w = close.tail(252).max()
    dd = (last - high_52w) / high_52w
    th = daily_move_threshold(ticker)

    sig = {}  # key -> (level, text)

    # 매수 / 관심
    if pd.notna(r) and r <= 35:
        sig["rsi_oversold"] = ("buy", f"RSI {r:.0f} 과매도 · 분할매수 타점 참고")
    if dd <= -0.15:
        sig["drawdown15"] = ("buy", f"52주 고점比 {dd*100:.0f}% · 조정 구간")
    if chg <= -th:
        sig["drop"] = ("buy", f"최근 종가 {chg*100:+.1f}% 급락")

    # 레짐 변화 — 펀드 holder 에게 가장 실질적
    if pd.notna(ma200) and pd.notna(ma200_prev):
        if prev >= ma200_prev and last < ma200:
            sig["break200_down"] = ("warn", "200일선 하향 이탈 · 추세 점검")
        if prev < ma200_prev and last >= ma200:
            sig["break200_up"] = ("buy", "200일선 회복 · 추세 전환")

    # 매도/주의 — 보유 종목만
    if cfg["holding"]:
        if pd.notna(r) and r >= 75:
            sig["rsi_overbought"] = ("sell", f"RSI {r:.0f} 과매수 · 차익실현 검토")
        if chg >= th:
            sig["surge"] = ("sell", f"최근 종가 {chg*100:+.1f}% 급등 · 차익실현 검토")
        if pd.notna(ma120) and not (ma20 > ma60 > ma120):
            sig["trend_break"] = ("warn", "단·중기 정배열 붕괴")

    # 변동성
    if cfg["vix"]:
        v = fetch_last(cfg["vix"])
        if v is not None and v >= cfg["vix_th"]:
            sig["vix"] = ("warn", f"변동성 급등 (VIX {v:.0f})")

    return sig, last


# ----------------------------------------------------------------------
# 상태 관리 (edge 트리거 + 쿨다운)
# ----------------------------------------------------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def diff_fire(prev_t, current_keys, today):
    """이번에 '새로' 참이 된 신호만 골라낸다.
       active = 직전 run 에서 이미 참이었는지. 쿨다운으로 깜빡임 재발송 차단."""
    fired, new_t = [], {}
    for key in current_keys:
        rec = prev_t.get(key, {})
        was_active = rec.get("active", False)
        last_fired = rec.get("last_fired")
        if was_active:
            # 진행 중인 에피소드 → 재발송 안 함, active 유지
            new_t[key] = {"active": True, "last_fired": last_fired}
            continue
        # 새 에피소드(직전 거짓 또는 처음) → 쿨다운 확인
        cooldown_ok = True
        if last_fired:
            cooldown_ok = (today - dt.date.fromisoformat(last_fired)).days >= COOLDOWN_DAYS
        if cooldown_ok:
            fired.append(key)
            new_t[key] = {"active": True, "last_fired": today.isoformat()}
        else:
            # 쿨다운으로 보류 → active 는 False 유지(쿨다운 지나면 그때 발송)
            new_t[key] = {"active": False, "last_fired": last_fired}
    # 직전엔 참이었지만 지금은 거짓 → 해소됨(active=False). last_fired 는 쿨다운용으로 보존
    for key, rec in prev_t.items():
        if key not in current_keys:
            new_t[key] = {"active": False, "last_fired": rec.get("last_fired")}
    return fired, new_t


# ----------------------------------------------------------------------
# 카카오 (나에게 보내기)
# ----------------------------------------------------------------------
def refresh_access_token():
    r = requests.post("https://kauth.kakao.com/oauth/token", data={
        "grant_type": "refresh_token",
        "client_id": os.environ["KAKAO_REST_API_KEY"],
        "refresh_token": os.environ["KAKAO_REFRESH_TOKEN"],
        "client_secret": os.environ["KAKAO_CLIENT_SECRET"],
    }, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data["access_token"], data.get("refresh_token")  # refresh 는 회전될 때만 옴


def send_kakao(access_token, text):
    template = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": DASHBOARD_URL, "mobile_web_url": DASHBOARD_URL},
        "button_title": "대시보드 열기",
    }
    r = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=10,
    )
    r.raise_for_status()


def chunk_send(access_token, full_text, limit=190):
    """text 템플릿은 약 200자 제한이라 줄 단위로 잘라 순차 발송."""
    buf = ""
    for line in full_text.split("\n"):
        if buf and len(buf) + len(line) + 1 > limit:
            send_kakao(access_token, buf)
            buf = line
        else:
            buf = line if not buf else f"{buf}\n{line}"
    if buf:
        send_kakao(access_token, buf)


# ----------------------------------------------------------------------
# refresh token 회전 시 GitHub Secret 자동 갱신 (GH_PAT 있을 때만)
# ----------------------------------------------------------------------
def update_github_secret(name, value):
    pat = os.environ.get("GH_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")  # Actions 가 자동 주입
    if not pat or not repo:
        print("GH_PAT 미설정 → refresh token 자동 저장 생략(약 2개월 뒤 수동 갱신 필요)")
        return
    import base64
    from nacl import encoding, public
    h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
    key = requests.get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers=h, timeout=10).json()
    pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
    enc = base64.b64encode(public.SealedBox(pk).encrypt(value.encode())).decode()
    requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
        headers=h, json={"encrypted_value": enc, "key_id": key["key_id"]}, timeout=10
    ).raise_for_status()
    print("refresh token 갱신본 저장 완료")


# ----------------------------------------------------------------------
def main():
    today = dt.datetime.now(KST).date()
    state = load_state()

    access, new_refresh = refresh_access_token()
    if new_refresh and new_refresh != os.environ.get("KAKAO_REFRESH_TOKEN"):
        update_github_secret("KAKAO_REFRESH_TOKEN", new_refresh)

    blocks = []
    for ticker, cfg in MARKETS.items():
        try:
            close = fetch_close(ticker)
        except Exception as e:
            print(f"[{cfg['name']}] 조회 실패 → 스킵: {e}")
            continue
        if close is None:
            print(f"[{cfg['name']}] 데이터 없음 → 스킵 (티커 확인: {ticker})")
            continue

        sig, price = evaluate(ticker, cfg, close)
        fired, new_t = diff_fire(state.get(ticker, {}), set(sig.keys()), today)
        state[ticker] = new_t

        if fired:
            lines = [f"{cfg['flag']}[{cfg['name']}] {cfg['index']} {price:,.0f}"]
            lines += [f" {TAG[sig[k][0]]} {sig[k][1]}" for k in fired]
            blocks.append("\n".join(lines))
        print(f"[{cfg['name']}] 현재신호 {sorted(sig.keys())} / 신규 {fired}")

    save_state(state)

    if not blocks:
        print("발송할 신규 신호 없음")
        return

    header = (f"📊 글로벌 증시 알림 {today:%m/%d}\n"
              f"확정 종가 기준 · 펀드 컷오프 {FUND_CUTOFF} KST 전 검토\n")
    footer = "\n※ 펀드는 미래 영업일 기준가로 체결 · 즉시매매 아님"
    body = header + "\n".join(blocks) + footer
    chunk_send(access, body)
    print("발송 완료\n" + body)


if __name__ == "__main__":
    main()
