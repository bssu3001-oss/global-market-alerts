def _fmt_price_line(price, change_pct):
    if change_pct is None:
        return f"현재가 {price:,.0f}원"
    return f"현재가 {price:,.0f}원 ({change_pct:+.1f}%)"


def check_alerts(quote, scenario, state, today):
    """
    quote: {"price": ..., "change_pct": ...} (fetch_quote() 결과)
    scenario: evaluate()가 반환한 scenario dict (entries, target)
    state: {"date": "YYYY-MM-DD", "fired": [...]}
    today: "YYYY-MM-DD" (오늘 날짜, KST 기준)

    반환: (triggered, new_state)
      triggered: [(key, level, message), ...] 새로 트리거된 알림만
      new_state: 갱신된 state (호출자가 저장해야 함)
    """
    price = quote.get("price") if quote else None
    if price is None:
        return [], state

    change_pct = quote.get("change_pct") if quote else None

    if not state or state.get("date") != today:
        fired = set()
    else:
        fired = set(state.get("fired", []))

    triggered = []

    entries = (scenario or {}).get("entries") or []
    for i, level in enumerate(entries[:4]):
        key = f"support_{i}"
        if key in fired or level is None:
            continue
        if price <= level:
            msg = (
                f"🟢 {i + 1}차 지지선 {level:,.0f}원 터치 — 분할매수 검토\n"
                + _fmt_price_line(price, change_pct)
            )
            triggered.append((key, level, msg))
            fired.add(key)

    target = (scenario or {}).get("target")
    key = "resistance"
    if key not in fired and target is not None and price >= target:
        msg = (
            f"🔴 저항선 {target:,.0f}원 도달 — 익절/매도 검토\n"
            + _fmt_price_line(price, change_pct)
        )
        triggered.append((key, target, msg))
        fired.add(key)

    new_state = {"date": today, "fired": sorted(fired)}
    return triggered, new_state
