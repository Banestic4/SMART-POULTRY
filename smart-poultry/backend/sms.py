"""SMS notification layer.

Sends through Termii's REST API. If SMS is disabled or not configured, the call
returns ('skipped', reason) and the alert is still recorded in the database and
shown on the dashboard, so the system never crashes because SMS is unavailable.
"""
# import requests
import requests
url = "https://BASE_URL/api/sms/send"
payload = {
          "to": "2348125012099",
           "from": "smart-poultry",
           "sms": "Hi there, you have a farm alert ",
           "type": "plain",
           "channel": "generic",
           "api_key": "tlv_zJAH7VF6MJxxOizmvOz7dHWZBd7F95ftOBq4ovM60t8",
       }
headers = {
'Content-Type': 'application/json',
}
response = requests.request("POST", url, headers=headers, json=payload)
print(response.text)

import config


def send_sms(text):
    """Return (status, detail). status is one of: sent, failed, skipped."""
    if not config.SMS_ENABLED:
        return "skipped", "SMS disabled (SP_SMS_ENABLED=0)"
    if config.SMS_PROVIDER != "termii":
        return "skipped", f"Unsupported provider {config.SMS_PROVIDER}"
    if not config.SMS_API_KEY or not config.SMS_RECIPIENTS:
        return "skipped", "SMS API key or recipient not configured"

    url = config.SMS_BASE_URL.rstrip("/") + "/api/sms/send"
    results, ok = [], 0
    for number in config.SMS_RECIPIENTS:
        payload = {
            "api_key": config.SMS_API_KEY,
            "to": number,
            "from": config.SMS_SENDER_ID,
            "sms": text[:300],
            "type": "plain",
            "channel": config.SMS_CHANNEL,
        }
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
    status = "sent" if ok == len(config.SMS_RECIPIENTS) else ("failed" if ok == 0 else "sent")
    return status, "; ".join(results)
