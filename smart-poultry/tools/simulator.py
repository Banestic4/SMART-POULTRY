"""Sensor simulator: posts readings to the backend exactly like the ESP32 does.

Use it (a) to develop/test without hardware, and (b) as a safety net in the defence if the
sensors misbehave. ALWAYS tell the panel when you are using simulated data.

    python simulator.py --scenario normal
    python simulator.py --scenario heat --interval 2
Scenarios: normal | heat | cold | humid | gas | mixed | cycle (normal -> heat -> gas -> mixed)
"""
import argparse
import random
import time

import requests

P = {  # (temp mean, hum mean, gas_raw mean)
    "normal": (26.5, 60, 1100),
    "heat": (34.5, 62, 1200),
    "cold": (15.5, 60, 1100),
    "humid": (27.0, 82, 1200),
    "gas": (27.0, 62, 2700),
    "mixed": (33.5, 80, 2800),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5000")
    ap.add_argument("--key", default="sp-device-key-123")
    ap.add_argument("--scenario", default="normal", choices=list(P) + ["cycle"])
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--count", type=int, default=0, help="0 = run until Ctrl+C")
    a = ap.parse_args()
    order = ["normal", "heat", "gas", "mixed"]
    i = 0
    while True:
        sc = a.scenario if a.scenario != "cycle" else order[(i // 15) % len(order)]
        t, h, g = P[sc]
        body = {"device_id": "simulator", "temperature": round(random.gauss(t, 0.4), 1),
                "humidity": round(min(100, max(0, random.gauss(h, 1.5))), 1),
                "gas_raw": int(min(4095, max(0, random.gauss(g, 40))))}
        try:
            r = requests.post(a.url + "/api/readings", json=body, headers={"X-API-Key": a.key}, timeout=5)
            print(sc, body, "->", r.status_code, r.json())
        except requests.RequestException as exc:
            print("server unreachable:", exc)
        i += 1
        if a.count and i >= a.count:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
