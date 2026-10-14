"""SMART-Poultry backend (Flask + SQLite).

Run:  python app.py
"""
import io
import os
import time
import uuid
from functools import wraps

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)
from PIL import Image
from werkzeug.security import check_password_hash

import ai
import config
import sms
from db import get_db, init_db

app = Flask(__name__)
app.config.update(
    SECRET_KEY=config.SECRET_KEY,
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,          # reject uploads > 5 MB
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
os.makedirs(config.MODEL_DIR, exist_ok=True)

_failed = {}          # ip -> (count, first_failure_time)
ALERT_DEDUP_S = 60    # do not store the same alert type more than once a minute


# ----------------------------------------------------------------------------
# Authentication helpers
# ----------------------------------------------------------------------------
def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="authentication required"), 401
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper


def device_key_ok():
    return request.headers.get("X-API-Key", "") == config.DEVICE_API_KEY


def locked_out(ip):
    rec = _failed.get(ip)
    if not rec:
        return False
    count, first = rec
    if time.time() - first > config.LOCKOUT_SECONDS:
        _failed.pop(ip, None)
        return False
    return count >= config.MAX_LOGIN_ATTEMPTS


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    ip = request.remote_addr
    if request.method == "POST":
        if locked_out(ip):
            error = "Too many failed attempts. Try again in a few minutes."
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            conn = get_db()
            row = conn.execute("SELECT * FROM Users WHERE username = ?", (username,)).fetchone()
            conn.close()
            if row and check_password_hash(row["password_hash"], password):
                _failed.pop(ip, None)
                session.clear()
                session["user"] = row["username"]
                session["role"] = row["role"]
                return redirect(url_for("dashboard"))
            count, first = _failed.get(ip, (0, time.time()))
            _failed[ip] = (count + 1, first)
            error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", user=session["user"], role=session.get("role", "farmer"))


# ----------------------------------------------------------------------------
# Alert engine
# ----------------------------------------------------------------------------
def evaluate_thresholds(t, h, gas_raw):
    """Return a list of (alert_type, severity, message)."""
    out = []
    if t >= config.TEMP_HIGH:
        out.append(("heat_stress", "critical", f"Heat stress: temperature {t:.1f} C (limit {config.TEMP_HIGH:.0f} C)."))
    elif t < config.TEMP_LOW:
        out.append(("cold_stress", "warning", f"Cold stress: temperature {t:.1f} C (below {config.TEMP_LOW:.0f} C)."))
    if h > config.HUM_HIGH:
        out.append(("high_humidity", "warning", f"High humidity {h:.0f}% (limit {config.HUM_HIGH:.0f}%)."))
    elif h < config.HUM_LOW:
        out.append(("low_humidity", "warning", f"Low humidity {h:.0f}% (below {config.HUM_LOW:.0f}%)."))
    if gas_raw >= config.GAS_HIGH_RAW:
        out.append(("poor_air_quality", "critical", f"Poor air quality: MQ135 reading {gas_raw} (limit {config.GAS_HIGH_RAW})."))
    return out


def raise_alert(conn, alert_type, severity, message, reading_id):
    """Store an alert (de-duplicated) and try to send an SMS (cool-down protected)."""
    recent = conn.execute(
        "SELECT 1 FROM Alerts WHERE alert_type = ? AND created_at > datetime('now', ?) LIMIT 1",
        (alert_type, f"-{ALERT_DEDUP_S} seconds")).fetchone()
    if recent:
        return None
    sent_recently = conn.execute(
        "SELECT 1 FROM Alerts WHERE alert_type = ? AND sms_status = 'sent' AND created_at > datetime('now', ?) LIMIT 1",
        (alert_type, f"-{config.SMS_COOLDOWN_S} seconds")).fetchone()
    if sent_recently:
        status, detail = "skipped", "SMS cool-down active"
    else:
        status, detail = sms.send_sms("SMART-POULTRY ALERT: " + message)
    cur = conn.execute(
        "INSERT INTO Alerts (alert_type, severity, message, reading_id, sms_status, sms_detail) VALUES (?,?,?,?,?,?)",
        (alert_type, severity, message, reading_id, status, detail))
    return cur.lastrowid


# ----------------------------------------------------------------------------
# Device endpoint (ESP32 -> backend)
# ----------------------------------------------------------------------------
def _num(payload, key, lo, hi, cast=float):
    try:
        v = cast(payload[key])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"missing or invalid '{key}'")
    if not (lo <= v <= hi) or v != v:
        raise ValueError(f"'{key}' out of range {lo}..{hi}")
    return v


@app.route("/api/readings", methods=["POST"])
def post_reading():
    if not device_key_ok():
        return jsonify(error="invalid device key"), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="JSON body required"), 400
    try:
        t = _num(payload, "temperature", -40, 80)
        h = _num(payload, "humidity", 0, 100)
        gas_raw = _num(payload, "gas_raw", 0, 4095, int)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    device_id = str(payload.get("device_id", "esp32-01"))[:32]
    gas_pct = round(gas_raw / 4095 * 100, 1)

    prob, label = ai.predict_environment(t, h, gas_pct)
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO Sensor_Readings (device_id, temperature, humidity, gas_raw, gas_pct, risk_prob, risk_label) VALUES (?,?,?,?,?,?,?)",
        (device_id, t, h, gas_raw, gas_pct, prob, label))
    rid = cur.lastrowid
    if prob is not None:
        conn.execute("INSERT INTO AI_Results (kind, ref_id, prediction, confidence) VALUES ('environment', ?, ?, ?)",
                     (rid, label, prob))
    raised = []
    for a_type, sev, msg in evaluate_thresholds(t, h, gas_raw):
        if raise_alert(conn, a_type, sev, msg, rid):
            raised.append(a_type)
    if label == "At-risk":
        msg = f"AI model predicts elevated disease-risk conditions (probability {prob * 100:.0f}%)."
        if raise_alert(conn, "ai_risk", "warning", msg, rid):
            raised.append("ai_risk")
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=rid, risk_prob=prob, risk_label=label, alerts=raised), 201


# ----------------------------------------------------------------------------
# Dashboard data endpoints (login required)
# ----------------------------------------------------------------------------
@app.route("/api/latest")
@login_required
def latest():
    conn = get_db()
    row = conn.execute(
        "SELECT *, CAST(strftime('%s','now') AS INTEGER) - CAST(strftime('%s', created_at) AS INTEGER) AS age_s "
        "FROM Sensor_Readings ORDER BY id DESC LIMIT 1").fetchone()
    counts = conn.execute(
        "SELECT (SELECT COUNT(*) FROM Sensor_Readings) AS readings, (SELECT COUNT(*) FROM Alerts) AS alerts").fetchone()
    conn.close()
    data = dict(row) if row else None
    online = bool(data) and data["age_s"] <= config.DEVICE_TIMEOUT_S
    return jsonify(reading=data, online=online, readings_total=counts["readings"], alerts_total=counts["alerts"],
                   thresholds=dict(temp_high=config.TEMP_HIGH, temp_low=config.TEMP_LOW, hum_high=config.HUM_HIGH,
                                   hum_low=config.HUM_LOW, gas_high_raw=config.GAS_HIGH_RAW),
                   models=dict(env=bool(ai._env), cv=ai.cv_available()))


@app.route("/api/history")
@login_required
def history():
    limit = min(max(request.args.get("limit", 120, type=int), 1), 2000)
    conn = get_db()
    rows = conn.execute(
        "SELECT id, temperature, humidity, gas_raw, gas_pct, risk_prob, risk_label, created_at "
        "FROM Sensor_Readings ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in reversed(rows)])


@app.route("/api/alerts")
@login_required
def alerts():
    limit = min(max(request.args.get("limit", 25, type=int), 1), 200)
    conn = get_db()
    rows = conn.execute("SELECT * FROM Alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/test-sms", methods=["POST"])
@login_required
def test_sms():
    status, detail = sms.send_sms("SMART-POULTRY test message: SMS alerts are working.")
    return jsonify(status=status, detail=detail)


# ----------------------------------------------------------------------------
# Image analysis (dashboard upload now; ESP32-CAM can POST here with the device key)
# ----------------------------------------------------------------------------
@app.route("/api/image", methods=["POST"])
def post_image():
    if "user" not in session and not device_key_ok():
        return jsonify(error="authentication required"), 401
    f = request.files.get("image")
    if not f:
        return jsonify(error="no file field named 'image'"), 400
    raw = f.read()
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return jsonify(error="not a valid image"), 400
    name = f"{uuid.uuid4().hex}.jpg"
    img.save(os.path.join(config.UPLOAD_DIR, name), "JPEG", quality=90)
    source = "dashboard" if "user" in session else "device"
    conn = get_db()
    img_id = conn.execute("INSERT INTO Images (filename, source) VALUES (?,?)", (name, source)).lastrowid
    label, conf = ai.classify_image(img)
    if label is None:
        conn.commit(); conn.close()
        return jsonify(ok=True, id=img_id, prediction=None,
                       note="Image stored, but the image model is not trained yet (run ml/train_cv.py)."), 201
    conn.execute("INSERT INTO AI_Results (kind, ref_id, prediction, confidence) VALUES ('image', ?, ?, ?)",
                 (img_id, label, conf))
    if not any(w in label.lower() for w in ("healthy", "normal")) and conf >= 0.60:
        raise_alert(conn, "image_abnormal", "warning",
                    f"Image analysis flagged possible '{label}' (confidence {conf * 100:.0f}%).", None)
    conn.commit(); conn.close()
    return jsonify(ok=True, id=img_id, prediction=label, confidence=conf), 201


@app.route("/api/images")
@login_required
def list_images():
    conn = get_db()
    rows = conn.execute(
        "SELECT i.id, i.filename, i.source, i.created_at, r.prediction, r.confidence "
        "FROM Images i LEFT JOIN AI_Results r ON r.kind='image' AND r.ref_id=i.id ORDER BY i.id DESC LIMIT 8").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/uploads/<path:filename>")
@login_required
def uploads(filename):
    if "/" in filename or ".." in filename:
        abort(404)
    return send_from_directory(config.UPLOAD_DIR, filename)


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="file too large (max 5 MB)"), 413


if __name__ == "__main__":
    init_db()
    info = ai.load_models()
    conn = get_db()
    n_users = conn.execute("SELECT COUNT(*) FROM Users").fetchone()[0]
    conn.close()
    print("=" * 60)
    print("SMART-Poultry backend")
    print("  Environmental model :", info["env"] or "NOT TRAINED (run ml/train_models.py)")
    print("  Image model         :", "loaded" if info["cv"] else "not trained (optional)")
    print("  Users               :", n_users, "" if n_users else "-> run: python create_user.py")
    print("  SMS                 :", "configured" if (config.SMS_API_KEY and config.SMS_RECIPIENTS) else "NOT configured (alerts shown on dashboard only)")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, threaded=True)
