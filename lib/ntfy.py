import urllib.request


def send_ntfy(topic, message, click_url=None, timeout=10):
    """ntfy.sh로 푸시 알림 발송. 실패해도 예외를 던지지 않음(빌드가 죽으면 안 됨)."""
    if not topic:
        return False
    headers = {}
    if click_url:
        headers["Click"] = click_url
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        print(f"[ntfy] 발송 실패: {e}")
        return False
