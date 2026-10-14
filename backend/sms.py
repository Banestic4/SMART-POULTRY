"""SMS notification layer (Termii). Reads its settings from config.py / environment variables.
No code runs at import time, and the API key is never written in this file."""
import requests
import config


def send_sms(text):
    """Return (status, detail). status is one of: sent, failed, skipped."""
    if not config.SMS_ENABLED:
        return "skipped", "SMS disabled (SP_SMS_ENABLED=0)"
    if config.SMS_PROVIDER != "termii":
        return "skipped", f"Unsupported provider {config.SMS_PROVIDER}"
    if not config.SMS_API_KEY or not config.SMS_RECIPIENTS:
        return "skipped", "SMS API key or recipient not configured"
    if "BASE_URL" in config.SMS_BASE_URL:
        return "skipped", "SP_SMS_BASE_URL still a placeholder - use the base URL from your Termii dashboard"

    url = config.SMS_BASE_URL.rstrip("/") + "/api/sms/send"
    results, ok = [], 0
    for number in config.SMS_RECIPIENTS:
        payload = {"api_key": config.SMS_API_KEY, "to": number, "from": config.SMS_SENDER_ID,
                   "sms": text[:300], "type": "plain", "channel": config.SMS_CHANNEL}
        try:
            r = requests.post(url, json=payload, timeout=10)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.ok and str(body.get("code", "")).lower() == "ok":
                ok += 1
                results.append(f"{number}: ok")
            else:
                results.append(f"{number}: HTTP {r.status_code} {str(body)[:120]}")
        except requests.RequestException as exc:
            results.append(f"{number}: {type(exc).__name__}")
    return ("sent" if ok else "failed"), "; ".join(results)
