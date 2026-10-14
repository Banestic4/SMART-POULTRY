"""Black-box test suite for the SMART-Poultry backend (use the results in Chapter Four, Table 4.x).

Start the backend first (python app.py), then:
    python test_system.py --user admin --password <your password>
Note: the lock-out test deliberately fails logins from this machine; it unlocks after 5 minutes
(or restart the backend).
"""
import argparse
import io
import sys

import requests
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:5000")
ap.add_argument("--user", default="admin")
ap.add_argument("--password", required=True)
ap.add_argument("--key", default="sp-device-key-123")
a = ap.parse_args()
URL, KEY = a.url, {"X-API-Key": a.key}
results = []


def check(tid, desc, ok, detail=""):
    results.append((tid, desc, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {tid} {desc} {detail}")


def post_reading(t, h, g, key=KEY):
    return requests.post(URL + "/api/readings", json={"temperature": t, "humidity": h, "gas_raw": g}, headers=key, timeout=10)


# --- Device endpoint ---------------------------------------------------------
r = post_reading(26, 60, 1000, key={})
check("T01", "Reading without device key is rejected (401)", r.status_code == 401)
r = post_reading(26, 60, 1000, key={"X-API-Key": "wrong"})
check("T02", "Reading with wrong device key is rejected (401)", r.status_code == 401)
r = requests.post(URL + "/api/readings", json={"temperature": "abc", "humidity": 60, "gas_raw": 1}, headers=KEY)
check("T03", "Non-numeric temperature is rejected (400)", r.status_code == 400)
r = post_reading(26, 150, 1000)
check("T04", "Out-of-range humidity is rejected (400)", r.status_code == 400)
r = post_reading(26.5, 60, 1000)
check("T05", "Valid normal reading is stored (201)", r.status_code == 201 and r.json().get("risk_label") in ("Normal", None))
check("T06", "Normal reading raises no threshold alert", r.json().get("alerts") == [])
r = post_reading(36, 60, 1000)
check("T07", "High temperature reading accepted (alert checked in T14b)", r.status_code == 201)
r = post_reading(26, 60, 3000)
check("T08", "High MQ135 reading accepted (alert checked in T14c)", r.status_code == 201)

# --- Authentication ---------------------------------------------------------
s = requests.Session()
check("T09", "Dashboard data blocked without login (401)", s.get(URL + "/api/latest").status_code == 401)
r = s.get(URL + "/", allow_redirects=False)
check("T10", "Dashboard page redirects to login when signed out", r.status_code == 302)
r = s.post(URL + "/login", data={"username": a.user, "password": a.password}, allow_redirects=False)
check("T11", "Valid credentials sign in", r.status_code == 302)
r = s.get(URL + "/api/latest")
check("T12", "Latest reading available after login", r.status_code == 200 and r.json()["reading"] is not None)
check("T13", "History endpoint returns rows", len(s.get(URL + "/api/history?limit=10").json()) > 0)
alerts = s.get(URL + "/api/alerts?limit=100").json()
types = {x["alert_type"] for x in alerts}
check("T14", "Alerts endpoint returns rows", len(alerts) > 0)
check("T14b", "heat_stress alert was recorded", "heat_stress" in types)
check("T14c", "poor_air_quality alert was recorded", "poor_air_quality" in types)
check("T14d", "AI-risk alert was recorded", "ai_risk" in types)

# --- Images -----------------------------------------------------------------
buf = io.BytesIO(); Image.new("RGB", (64, 64), (200, 150, 100)).save(buf, "JPEG"); buf.seek(0)
r = s.post(URL + "/api/image", files={"image": ("t.jpg", buf, "image/jpeg")})
check("T15", "Valid image accepted", r.status_code == 201, str(r.json())[:80])
r = s.post(URL + "/api/image", files={"image": ("t.jpg", io.BytesIO(b"not an image"), "image/jpeg")})
check("T16", "Non-image file rejected (400)", r.status_code == 400)
r = requests.post(URL + "/api/image", files={"image": ("t.jpg", io.BytesIO(b"x"), "image/jpeg")})
check("T17", "Image upload without login/device key rejected (401)", r.status_code == 401)

# --- Brute-force lock-out (run last) -------------------------------------------
b = requests.Session(); locked = False
for _ in range(7):
    r = b.post(URL + "/login", data={"username": a.user, "password": "wrong-password"})
    if "Too many failed attempts" in r.text:
        locked = True
check("T18", "Repeated wrong passwords trigger temporary lock-out", locked)

passed = sum(1 for _, _, ok in results if ok)
print(f"\n{passed}/{len(results)} tests passed")
sys.exit(0 if passed == len(results) else 1)
