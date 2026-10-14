from flask import Flask, redirect, render_template_string, request, url_for, session, jsonify, send_from_directory, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3, random, os, re, sys, secrets, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai, sms, config   # AI model + SMS layer (same folder as this file)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / 'smart_poultry.db'
app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SMART_POULTRY_SECRET') or secrets.token_hex(32)  # set SMART_POULTRY_SECRET to keep sessions across restarts
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

TEMP_MIN, TEMP_MAX = 18.0, 32.0
HUMIDITY_MIN, HUMIDITY_MAX = 40.0, 75.0
GAS_WARNING = int(os.environ.get('SP_GAS_HIGH_RAW', 2200))  # MQ135 12-bit ADC value (0-4095). CALIBRATE: see README.
DEVICE_API_KEY = os.environ.get('SP_DEVICE_API_KEY', 'sp-device-key-123')  # must equal API_KEY in the firmware
DEVICE_TIMEOUT_S = 30
ALERT_DEDUP_S = 60
SMS_COOLDOWN_S = 300
MAX_LOGIN_ATTEMPTS, LOCKOUT_S = 5, 300
_fails = {}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'agent', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sensor_readings (
 id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at TEXT NOT NULL,
 temperature REAL NOT NULL, humidity REAL NOT NULL, gas_value INTEGER NOT NULL,
 data_source TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, reading_id INTEGER, recorded_at TEXT NOT NULL,
 message TEXT NOT NULL, severity TEXT NOT NULL,
 FOREIGN KEY (reading_id) REFERENCES sensor_readings(id)
);
CREATE TABLE IF NOT EXISTS chat_messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, role TEXT NOT NULL,
 message TEXT NOT NULL, response TEXT NOT NULL, recorded_at TEXT NOT NULL
);
'''

class AutoClose(sqlite3.Connection):
    # 'with connect_db() as db' now commits AND closes (the original leaked connections)
    def __exit__(self, *a):
        try: return super().__exit__(*a)
        finally: self.close()

def connect_db():
    db = sqlite3.connect(DATABASE, factory=AutoClose, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def now_text():
    return datetime.now().astimezone().isoformat(timespec='seconds')

def init_db():
    with connect_db() as db:
        db.executescript(SCHEMA)
        # migrate older database files: add the columns the new features need
        def addcol(table, col, decl):
            cols = [r['name'] for r in db.execute(f'PRAGMA table_info({table})')]
            if col not in cols: db.execute(f'ALTER TABLE {table} ADD COLUMN {col} {decl}')
        addcol('sensor_readings', 'device_id', 'TEXT')
        addcol('sensor_readings', 'risk_prob', 'REAL')
        addcol('alerts', 'alert_type', 'TEXT')
        addcol('alerts', 'sms_status', 'TEXT')
        addcol('alerts', 'sms_detail', 'TEXT')
        if not db.execute('SELECT id FROM users LIMIT 1').fetchone():
            pw = os.environ.get('SP_ADMIN_PASSWORD') or secrets.token_urlsafe(9)
            db.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)',
                       ('admin', generate_password_hash(pw), 'admin', now_text()))
            print(f'*** First run: created user admin with password: {pw}  (change it / set SP_ADMIN_PASSWORD) ***')

def threshold_alerts(temperature, humidity, gas_value):
    out=[]
    if temperature > TEMP_MAX: out.append(('heat_stress','CRITICAL',f'Temperature {temperature:.1f} °C is above the limit ({TEMP_MAX:g} °C).'))
    elif temperature < TEMP_MIN: out.append(('cold_stress','WARNING',f'Temperature {temperature:.1f} °C is below the limit ({TEMP_MIN:g} °C).'))
    if humidity > HUMIDITY_MAX: out.append(('high_humidity','WARNING',f'Relative humidity {humidity:.1f}% is above the limit ({HUMIDITY_MAX:g}%).'))
    elif humidity < HUMIDITY_MIN: out.append(('low_humidity','WARNING',f'Relative humidity {humidity:.1f}% is below the limit ({HUMIDITY_MIN:g}%).'))
    if gas_value >= GAS_WARNING: out.append(('poor_air_quality','CRITICAL',f'MQ135 raw signal {gas_value} reached the limit ({GAS_WARNING}); this is not a ppm measurement.'))
    return out

def analyse_reading(temperature, humidity, gas_value):
    return [m for _,_,m in threshold_alerts(temperature, humidity, gas_value)]

def _age_seconds(stamp):
    try: return (datetime.now().astimezone()-datetime.fromisoformat(stamp)).total_seconds()
    except Exception: return 1e9

def save_reading(temperature, humidity, gas_value, source='SIMULATED', device_id=None):
    gas_pct = round(gas_value/4095*100, 1)
    prob, label = ai.predict_environment(temperature, humidity, gas_pct)
    found = threshold_alerts(temperature, humidity, gas_value)
    if prob is not None and prob >= config.ML_RISK_THRESHOLD:
        found.append(('ai_risk','WARNING',f'AI model: environment at risk (probability {prob:.2f}).'))
    status = 'WARNING' if found else 'NORMAL'
    stamp = now_text()
    with connect_db() as db:
        cur = db.execute('INSERT INTO sensor_readings(recorded_at,temperature,humidity,gas_value,data_source,status,device_id,risk_prob) VALUES(?,?,?,?,?,?,?,?)',
                         (stamp,temperature,humidity,gas_value,source,status,device_id,prob))
        rid = cur.lastrowid
        for atype, sev, msg in found:
            last = db.execute('SELECT recorded_at FROM alerts WHERE alert_type=? ORDER BY id DESC LIMIT 1',(atype,)).fetchone()
            if last and _age_seconds(last['recorded_at']) < ALERT_DEDUP_S: continue   # do not flood the list
            lastsms = db.execute("SELECT recorded_at FROM alerts WHERE alert_type=? AND sms_status='sent' ORDER BY id DESC LIMIT 1",(atype,)).fetchone()
            if lastsms and _age_seconds(lastsms['recorded_at']) < SMS_COOLDOWN_S: st, det = 'skipped', 'SMS cool-down active'
            else: st, det = sms.send_sms('SMART-POULTRY ALERT: '+msg)
            db.execute('INSERT INTO alerts(reading_id,recorded_at,message,severity,alert_type,sms_status,sms_detail) VALUES(?,?,?,?,?,?,?)',(rid,stamp,msg,sev,atype,st,det))
    return status, [m for _,_,m in found]

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'username' not in session: return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Administrator access is required for that page.', 'warning')
            return redirect(url_for('dashboard'))
        return fn(*args, **kwargs)
    return wrapper

LOGIN_PAGE = r'''
<!doctype html>
<html lang="en">

<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#071a25">
<link rel="manifest" href="{{ url_for('manifest') }}">
<link rel="icon" href="{{ url_for('static',filename='icon.svg') }}">
<title>SMART-Poultry</title>
<style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;min-height:100vh;font-family:Inter,Segoe UI,Arial,sans-serif;background:#06131de8 url('{{ url_for('static',filename='poultry-tech-bg.png') }}') center/cover fixed;color:#f2fbff;display:grid;place-items:center;padding:22px}body:before{content:"";position:fixed;inset:0;background:linear-gradient(115deg,rgba(2,12,22,.86),rgba(3,30,43,.55),rgba(4,12,23,.82));backdrop-filter:blur(2px)}.wrap{position:relative;width:min(100%,440px)}.brand{display:flex;align-items:center;gap:12px;margin:0 0 20px 4px}.logo{width:46px;height:46px;border-radius:15px;display:grid;place-items:center;background:linear-gradient(135deg,#21e6c1,#16a4ff);color:#06131d;font-size:24px;box-shadow:0 0 28px #1be6c155}.brand strong{font-size:19px;letter-spacing:.3px}.brand small{display:block;color:#a6c5d2;margin-top:4px}.panel{padding:34px;border:1px solid #9aefff38;border-radius:24px;background:rgba(5,22,33,.68);backdrop-filter:blur(22px);box-shadow:0 22px 80px #0008,0 0 35px #00d9ff12}.eyebrow{color:#45efd0;text-transform:uppercase;letter-spacing:2px;font-size:11px;font-weight:800}.panel h1{font-size:30px;margin:10px 0}.muted{color:#a7bdc8;line-height:1.55;font-size:14px}.field{display:block;margin-top:20px;font-size:13px;color:#c6dce5}.field input{display:block;width:100%;margin-top:8px;padding:14px 15px;border:1px solid #7cb3c34a;border-radius:12px;background:#071a26c9;color:#fff;outline:none}.field input:focus{border-color:#29e4cf;box-shadow:0 0 0 3px #29e4cf1b}.btn{width:100%;margin-top:24px;padding:14px;border:0;border-radius:12px;background:linear-gradient(100deg,#22e0bd,#168fff);color:#04151f;font-weight:800;cursor:pointer;box-shadow:0 0 25px #1ad7d52c}.note{font-size:12px;color:#8eabb9;line-height:1.6;margin-top:18px}.error{background:#ff53651c;color:#ffabb4;padding:10px;border-radius:9px;font-size:13px}.credentials{padding:12px;margin-top:14px;border:1px solid #b7eaf021;border-radius:10px;background:#e5fbff08;font-size:12px;line-height:1.7;color:#bbd2db}.credentials b{color:#e6faff}@media(max-width:480px){.panel{padding:25px}.panel h1{font-size:26px}}
</style>

</head>

<body>
<div class="wrap">
<div class="brand"><div class="logo">✦</div>
<div><strong>SMART-Poultry</strong>
<small>Iot & AI-assisted Poultry monitoring System</small>
</div>
</div>
<section class="panel">
<div class="eyebrow">Secure farm workspace</div>
<h1>Hello!, Welcome Back.</h1>
<p class="muted">Sign in to review environmental readings, monitor alerts and consult the farm-support assistant for informed decision making.</p>
{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}<p class="error">{{ message }}</p>
{% endfor %}
{% endwith %}

<form method="post">
<label class="field">Username<input name="username" autocomplete="username" required autofocus></label>
<label class="field">Password<input name="password" type="password" autocomplete="current-password" required></label>
<button class="btn" type="submit">Log In</button>
</form>

<p class="note">Prototype notice: readings may be simulated. The assistant provides general decision support and is not a substitute for a qualified poultry veterinarian.</p></section></div><script>if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/service-worker.js').catch(()=>{}));}</script></body></html>'''


DASHBOARD = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#071721"><meta name="description" content="SMART-Poultry environmental monitoring and early warning dashboard"><link rel="manifest" href="{{ url_for('manifest') }}"><link rel="icon" href="{{ url_for('static',filename='icon.svg') }}"><title>SMART-Poultry · Operations</title><script src="{{ url_for('static',filename='chart.umd.min.js') }}"></script><script>window.Chart||document.write('<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"><\/script>')</script><style>
:root{--bg:#07141d;--panel:#0d202b;--panel2:#102833;--text:#e8f7fb;--muted:#91aab6;--line:#6adfe51d;--cyan:#39e7e1;--green:#59f0bb;--blue:#579cff;--pink:#ff71c6;--orange:#ffbf69;--shadow:0 14px 38px #0003}body.light{--bg:#eef5f7;--panel:#fff;--panel2:#f5fafb;--text:#16313c;--muted:#607a84;--line:#214c5c1d;--shadow:0 12px 30px #23445512}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 80% 0%,#0e56532b,transparent 38%),var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif;transition:background .2s,color .2s}button,input,textarea{font:inherit}.layout{display:grid;grid-template-columns:245px minmax(0,1fr);min-height:100vh}.sidebar{border-right:1px solid var(--line);padding:25px 16px;background:color-mix(in srgb,var(--panel) 86%,transparent);display:flex;flex-direction:column;gap:25px}.brand{display:flex;align-items:center;gap:11px;padding:0 8px}.logo{height:42px;width:42px;border-radius:14px;display:grid;place-items:center;background:linear-gradient(135deg,var(--green),var(--cyan));color:#05232a;font-size:22px;box-shadow:0 0 24px #36e6d52b}.brand b{font-size:16px}.brand small{display:block;color:var(--muted);font-size:11px;margin-top:4px}.navlabel{color:var(--muted);font-size:10px;font-weight:800;letter-spacing:1.7px;padding:0 12px}.nav{display:grid;gap:6px}.nav a,.nav button{color:var(--muted);text-decoration:none;display:flex;gap:12px;align-items:center;padding:12px;border-radius:11px;border:0;background:transparent;text-align:left;cursor:pointer;font-size:13px}.nav a.active,.nav a:hover,.nav button:hover{background:#26d8ce15;color:var(--cyan)}.nav .ico{width:20px;text-align:center;font-size:16px}.sidebottom{margin-top:auto}.profile{padding:13px;background:var(--panel2);border:1px solid var(--line);border-radius:14px;display:flex;align-items:center;gap:10px}.avatar{height:34px;width:34px;border-radius:50%;display:grid;place-items:center;background:#1dcdbd22;color:var(--cyan);font-weight:800}.profile small{display:block;color:var(--muted);font-size:11px;margin-top:3px}.main{padding:28px clamp(16px,3vw,42px);min-width:0;max-width:1700px;width:100%;margin:auto}.topbar{display:flex;justify-content:space-between;gap:18px;align-items:center;margin-bottom:28px}.kicker{font-size:11px;text-transform:uppercase;letter-spacing:2px;color:var(--cyan);font-weight:800}.topbar h1{font-size:clamp(23px,3vw,32px);margin:7px 0}.sub{color:var(--muted);font-size:13px}.actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:1px solid var(--line);border-radius:10px;padding:10px 13px;background:var(--panel);color:var(--text);cursor:pointer;text-decoration:none;font-size:12px}.btn.primary{background:linear-gradient(100deg,#1ccdb5,#369fff);color:#05222b;border:0;font-weight:800}.btn:hover{filter:brightness(1.1)}.banner{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:20px 22px;border-radius:17px;margin-bottom:19px;background:linear-gradient(110deg,#0e716b,#103b55 75%,#192b50);border:1px solid #5df6d72a;box-shadow:0 8px 30px #00d9c20c}.banner h2{margin:0 0 6px;font-size:17px}.banner p{margin:0;color:#c5e8e9;font-size:12px;line-height:1.6}.live{white-space:nowrap;font-size:11px;color:#8fffd7}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#5df5b4;box-shadow:0 0 12px #5df5b4;margin-right:7px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:18px;box-shadow:var(--shadow);min-width:0}.metrichead{display:flex;align-items:center;justify-content:space-between;gap:8px;color:var(--muted);font-size:12px}.metricicon{width:36px;height:36px;border-radius:12px;display:grid;place-items:center;background:#36e5d414;color:var(--cyan);font-size:18px}.metric{font-size:clamp(24px,3vw,32px);font-weight:750;letter-spacing:-1px;margin:15px 0 8px}.unit{font-size:13px;color:var(--muted);font-weight:500;letter-spacing:0}.foot{font-size:11px;color:var(--muted)}.pill{font-size:10px;padding:5px 8px;border-radius:30px;background:#57e6b31a;color:var(--green);font-weight:800}.pill.warn{background:#ffbd6919;color:var(--orange)}.sectionhead{display:flex;justify-content:space-between;align-items:end;gap:10px;margin:27px 0 13px}.sectionhead h2{font-size:17px;margin:0 0 5px}.sectionhead p{margin:0;color:var(--muted);font-size:12px}.twocol{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,1fr);gap:14px}.cardtitle{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:18px}.cardtitle b{font-size:13px}.chartbox{height:245px;position:relative}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:540px;font-size:12px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.8px}td{color:var(--text)}.status{font-size:10px;font-weight:800;border-radius:6px;padding:5px 7px;background:#57e6b318;color:var(--green)}.status.warning{background:#ffbd691a;color:var(--orange)}.alertlist{display:grid;gap:10px}.alert{padding:12px;border:1px solid var(--line);border-radius:11px;display:flex;gap:10px;font-size:12px;line-height:1.5}.alerticon{color:var(--orange)}.alert small{display:block;color:var(--muted);margin-top:5px}.empty{color:var(--muted);font-size:12px;padding:12px 0}.assistant{display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,.85fr);gap:14px}.chatlog{height:255px;overflow:auto;display:flex;flex-direction:column;gap:10px;padding:4px 2px 14px}.bubble{max-width:94%;padding:11px 13px;border-radius:12px;font-size:12px;line-height:1.55;white-space:pre-wrap}.bubble.bot{background:var(--panel2);border:1px solid var(--line);align-self:flex-start}.bubble.user{background:#16bca91b;border:1px solid #35e3d52b;align-self:flex-end}.chatform{display:flex;gap:8px}.chatform input{flex:1;min-width:0;padding:12px;border-radius:10px;border:1px solid var(--line);background:var(--panel2);color:var(--text);outline:none}.quickprompts{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.quickprompts button{font-size:10px;border:1px solid var(--line);background:transparent;color:var(--muted);padding:7px 9px;border-radius:20px;cursor:pointer}.footer{color:var(--muted);font-size:10px;line-height:1.6;margin:24px 0}.flash{padding:11px 14px;border-radius:10px;background:#ffbd6915;color:var(--orange);margin-bottom:14px;font-size:12px}.mobiletop{display:none}@media(max-width:1100px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.twocol,.assistant{grid-template-columns:1fr}}@media(max-width:760px){.layout{grid-template-columns:1fr}.sidebar{display:none}.main{padding:17px 14px}.topbar{align-items:flex-start;flex-direction:column}.banner{align-items:flex-start;flex-direction:column}.mobiletop{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.grid{gap:9px}.card{padding:14px}.metric{font-size:25px}.sectionhead{margin-top:22px}.chartbox{height:220px}}@media(max-width:380px){.grid{grid-template-columns:1fr}.actions .btn{flex:1}.metric{font-size:28px}}
</style></head><body><div class="layout"><aside class="sidebar"><div class="brand"><div class="logo">✦</div><div><b>SMART-Poultry</b><small>Intelligent farm system</small></div></div><div class="navlabel">WORKSPACE</div><nav class="nav"><a class="active" href="#overview"><span class="ico">◈</span>Overview</a><a href="#environment"><span class="ico">⌁</span>Environment</a><a href="#alerts"><span class="ico">♧</span>Alerts & activity</a><a href="#assistant"><span class="ico">✧</span>AI farm assistant</a>{% if role == 'admin' %}<a href="#admin"><span class="ico">⚙</span>Admin overview</a>{% endif %}</nav><div class="sidebottom"><div class="navlabel">PREFERENCES</div><nav class="nav"><button onclick="toggleTheme()"><span class="ico">◐</span><span id="themeLabel">Switch theme</span></button><a href="{{ url_for('logout') }}"><span class="ico">↪</span>Sign out</a></nav><div class="profile"><div class="avatar">{{ username[0]|upper }}</div><div><b style="font-size:12px">{{ username }}</b><small>{{ role|title }} account</small></div></div></div></aside><main class="main"><div class="mobiletop"><div class="brand"><div class="logo">✦</div><div><b>SMART-Poultry</b><small>Farm intelligence</small></div></div><button class="btn" onclick="toggleTheme()">◐ Theme</button></div><header class="topbar"><div><div class="kicker">Farm operations / Overview</div><h1>Good day, {{ username|title }} <span style="color:var(--green)">✦</span></h1><div class="sub">Environmental intelligence for a healthier flock · {{ today }}</div></div><div class="actions"><button class="btn" onclick="location.reload()">↻ Refresh</button><a class="btn" href="{{ url_for('export_csv') }}">↓ Export CSV</a><button class="btn" onclick="fetch('/api/test-sms',{method:'POST'}).then(r=>r.json()).then(d=>alert('SMS: '+d.status+' - '+d.detail))">✉ Test SMS</button>{% if role == 'admin' %}<a class="btn primary" href="#admin">Admin view ↗</a>{% endif %}</div></header>{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="flash">{{ message }}</div>{% endfor %}{% endwith %}<section class="banner"><div><h2>Early signals. Better decisions.</h2><p>Monitor temperature, relative humidity and gas-sensor signals, then investigate warnings before they become overlooked farm risks.</p></div><div class="live"><span class="dot"></span>{{ {'HARDWARE':'LIVE SENSOR DATA','STALE':'SENSOR OFFLINE · showing last reading'}.get(data_mode,'DEMO DATA MODE') }}</div></section><section id="overview" class="grid"><article class="card"><div class="metrichead"><span>Temperature</span><span class="metricicon">♨</span></div><div class="metric">{{ '%.1f'|format(latest.temperature) if latest else '—' }} <span class="unit">°C</span></div><div class="foot">Configured demo range: 18–32 °C</div></article><article class="card"><div class="metrichead"><span>Relative humidity</span><span class="metricicon">◉</span></div><div class="metric">{{ '%.1f'|format(latest.humidity) if latest else '—' }} <span class="unit">%</span></div><div class="foot">Configured demo range: 40–75%</div></article><article class="card"><div class="metrichead"><span>Gas sensor signal</span><span class="metricicon">≋</span></div><div class="metric">{{ latest.gas_value if latest else '—' }} <span class="unit">raw</span></div><div class="foot">Raw signal only; not ppm</div></article><article class="card"><div class="metrichead"><span>Environmental status</span><span class="metricicon">⌁</span></div><div class="metric" style="font-size:23px"><span class="pill {{ 'warn' if latest and latest.status == 'WARNING' else '' }}">{{ latest.status if latest else 'NO DATA' }}</span></div><div class="foot">{{ 'Latest reading · ' ~ latest.recorded_at if latest else 'Generate a test reading to begin' }}</div></article></section><div class="sectionhead" id="environment"><div><h2>Environmental trends</h2><p>Recent stored readings · demo values are labelled as simulated</p></div><span class="pill">{{ readings|length }} records</span></div><section class="twocol"><article class="card"><div class="cardtitle"><b>Temperature & humidity</b><span class="foot">Recent samples</span></div><div class="chartbox"><canvas id="trendChart" aria-label="Temperature and humidity trend chart"></canvas></div></article><article class="card"><div class="cardtitle"><b>Reading status</b><span class="foot">Normal vs warning</span></div><div class="chartbox"><canvas id="statusChart" aria-label="Reading status chart"></canvas></div><p class="foot">Status is based on configurable prototype thresholds, not a validated veterinary standard.</p></article></section><div class="sectionhead" id="alerts"><div><h2>Alerts & recent readings</h2><p>Review unusual values and the source of each record</p></div><div class="actions"><form action="{{ url_for('generate_normal') }}" method="post"><button class="btn" type="submit">＋ Normal test</button></form><form action="{{ url_for('generate_abnormal') }}" method="post"><button class="btn primary" type="submit">＋ Warning test</button></form></div></div><section class="twocol"><article class="card"><div class="cardtitle"><b>Latest readings</b><a class="btn" href="{{ url_for('export_csv') }}">Export</a></div><div class="tablewrap"><table><thead><tr><th>Recorded</th><th>Temp</th><th>Humidity</th><th>Gas raw</th><th>Source</th><th>Status</th></tr></thead><tbody>{% for r in readings %}<tr><td>{{ r.recorded_at[11:19] if r.recorded_at|length > 18 else r.recorded_at }}</td><td>{{ '%.1f'|format(r.temperature) }}°</td><td>{{ '%.1f'|format(r.humidity) }}%</td><td>{{ r.gas_value }}</td><td>{{ r.data_source }}</td><td><span class="status {{ 'warning' if r.status == 'WARNING' else '' }}">{{ r.status }}</span></td></tr>{% else %}<tr><td colspan="6">No readings yet. Use a test button to add a sample.</td></tr>{% endfor %}</tbody></table></div></article><article class="card"><div class="cardtitle"><b>Recent alerts</b><span class="pill {{ 'warn' if alerts else '' }}">{{ alerts|length }} recent</span></div><div class="alertlist">{% for a in alerts %}<div class="alert"><div class="alerticon">⚠</div><div>{{ a.message }}<small>{{ a.recorded_at }} · {{ a.severity }} · SMS: {{ a.sms_status or 'n/a' }}</small></div></div>{% else %}<div class="empty">No alerts recorded. This does not guarantee that the flock or environment is risk-free.</div>{% endfor %}</div></article></section><div class="sectionhead" id="assistant"><div><h2>AI farm-support assistant</h2><p>Ask about readings, alerts, and sensible next checks</p></div><span class="pill">Rule-based guidance</span></div><section class="assistant"><article class="card"><div class="cardtitle"><b>Chat with the farm assistant</b><span class="foot">Decision support only</span></div><div id="chatlog" class="chatlog" aria-live="polite"><div class="bubble bot">Hello {{ username }}. I can explain the latest recorded readings, help interpret dashboard alerts, and suggest practical checks. I cannot diagnose disease or replace a veterinarian.</div></div><form class="chatform" id="chatform"><input id="question" maxlength="700" placeholder="Ask: What does this warning mean?" required autocomplete="off"><button class="btn primary" type="submit">Ask ↗</button></form><div class="quickprompts"><button type="button" data-q="Summarise the latest readings">Summarise readings</button><button type="button" data-q="What should I check when temperature is high?">High temperature</button><button type="button" data-q="Explain the gas sensor warning">Gas warning</button><button type="button" data-q="What are the limitations of these readings?">Data limitations</button></div></article><article class="card"><div class="cardtitle"><b>Assistant guidance</b><span class="metricicon">✧</span></div><div class="alertlist"><div class="alert"><div class="alerticon">◉</div><div><b>Check the context</b><small>Compare readings with the flock's age, stocking density, ventilation, water access and recent behaviour.</small></div></div><div class="alert"><div class="alerticon">⌁</div><div><b>Verify the sensor</b><small>Check placement, wiring, calibration and whether the value is simulated or from physical hardware.</small></div></div><div class="alert"><div class="alerticon">＋</div><div><b>Escalate when needed</b><small>For unusual mortality, severe distress or persistent illness signs, contact a qualified poultry veterinarian promptly.</small></div></div></div><p class="foot" style="margin-top:14px">This built-in assistant uses local rules and dashboard data. It is not connected to a hosted AI model and should not be presented as one.</p></article></section>{% if role == 'admin' %}<div class="sectionhead" id="admin"><div><h2>Administrator overview</h2><p>Local prototype account and data summary</p></div><span class="pill">ADMIN</span></div><section class="grid"><article class="card"><div class="metrichead">Registered accounts</div><div class="metric">{{ user_count }}</div><div class="foot">Admin and agent demo accounts</div></article><article class="card"><div class="metrichead">Stored readings</div><div class="metric">{{ total_readings }}</div><div class="foot">All sources combined</div></article><article class="card"><div class="metrichead">Warnings recorded</div><div class="metric">{{ total_alerts }}</div><div class="foot">Historical alert rows</div></article><article class="card"><div class="metrichead">Current data mode</div><div class="metric" style="font-size:20px">{{ data_mode }}</div><div class="foot">Mode follows recorded reading source</div></article></section>{% endif %}<p class="footer">SMART-Poultry prototype · Software thresholds are illustrative and must be validated before operational use. Gas values are raw sensor signals, not calibrated concentrations. The dashboard is decision support, not veterinary diagnosis.</p></main></div><script>
const labels={{ chart_labels|tojson }};const temps={{ chart_temps|tojson }};const hums={{ chart_hums|tojson }};const statuses={{ chart_statuses|tojson }};let dark=true;try{dark=localStorage.getItem('sp-theme')!=='light'}catch(e){}if(!dark)document.body.classList.add('light');function toggleTheme(){document.body.classList.toggle('light');dark=!document.body.classList.contains('light');try{localStorage.setItem('sp-theme',dark?'dark':'light')}catch(e){}if(window.trendChart){const c=document.body.classList.contains('light')?'#607a84':'#91aab6';trendChart.options.scales.x.ticks.color=c;trendChart.options.scales.y.ticks.color=c;trendChart.update();}}
document.getElementById('themeLabel')&&(document.getElementById('themeLabel').textContent=dark?'Switch to light theme':'Switch to dark theme');
if(window.Chart){Chart.defaults.color=getComputedStyle(document.body).getPropertyValue('--muted').trim();Chart.defaults.font.family='Inter, Segoe UI, Arial';window.trendChart=new Chart(document.getElementById('trendChart'),{type:'line',data:{labels,datasets:[{label:'Temperature °C',data:temps,borderColor:'#39e7e1',backgroundColor:'#39e7e11c',fill:true,tension:.36,yAxisID:'y'},{label:'Humidity %',data:hums,borderColor:'#579cff',backgroundColor:'#579cff12',fill:false,tension:.36,yAxisID:'y1'}]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{labels:{usePointStyle:true,boxWidth:7}}},scales:{x:{grid:{color:'#8baeb010'}},y:{beginAtZero:false,grid:{color:'#8baeb015'}},y1:{position:'right',grid:{drawOnChartArea:false}}}}});new Chart(document.getElementById('statusChart'),{type:'doughnut',data:{labels:['Normal','Warning'],datasets:[{data:[statuses.filter(s=>s==='NORMAL').length,statuses.filter(s=>s==='WARNING').length],backgroundColor:['#59f0bb','#ffbf69'],borderColor:getComputedStyle(document.body).getPropertyValue('--panel').trim(),borderWidth:4,hoverOffset:6}]},options:{responsive:true,maintainAspectRatio:false,cutout:'72%',plugins:{legend:{position:'bottom',labels:{usePointStyle:true,boxWidth:8,padding:20}}}}});}
window.__lastId={{ latest.id if latest else 0 }};setInterval(()=>{if(document.activeElement===document.getElementById('question')||document.querySelectorAll('#chatlog .bubble').length>1)return;fetch('/api/latest').then(r=>r.json()).then(d=>{if(d.id&&d.id!==window.__lastId)location.reload()}).catch(()=>{})},4000);
const log=document.getElementById('chatlog'),form=document.getElementById('chatform'),input=document.getElementById('question');function addBubble(text,who){const el=document.createElement('div');el.className='bubble '+who;el.textContent=text;log.appendChild(el);log.scrollTop=log.scrollHeight;}async function ask(q){if(!q.trim())return;addBubble(q,'user');input.value='';try{const res=await fetch('{{ url_for("assistant_api") }}',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});const data=await res.json();addBubble(data.response||data.error||'No response returned.','bot')}catch(e){addBubble('I could not reach the local assistant endpoint. Refresh the page and try again.','bot')}}form.addEventListener('submit',e=>{e.preventDefault();ask(input.value)});document.querySelectorAll('[data-q]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.q)));if('serviceWorker'in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/service-worker.js').catch(()=>{}));}
</script></body></html>'''

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username=request.form.get('username','').strip()[:80]
        password=request.form.get('password','')
        ip=request.remote_addr
        n,until=_fails.get(ip,(0,0))
        if until>time.time():
            flash('Too many failed attempts. Try again in a few minutes.','error'); return render_template_string(LOGIN_PAGE)
        with connect_db() as db: user=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        if user and check_password_hash(user['password_hash'],password):
            _fails.pop(ip,None); session.clear(); session['username']=user['username']; session['role']=user['role']
            return redirect(url_for('dashboard'))
        n+=1; _fails[ip]=(n, time.time()+LOCKOUT_S if n>=MAX_LOGIN_ATTEMPTS else 0)
        flash('Username or password was not recognised.','error')
    return render_template_string(LOGIN_PAGE)

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    with connect_db() as db:
        latest=db.execute('SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 1').fetchone()
        readings=db.execute('SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 12').fetchall()
        alerts=db.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT 8').fetchall()
        total_readings=db.execute('SELECT COUNT(*) n FROM sensor_readings').fetchone()['n']
        total_alerts=db.execute('SELECT COUNT(*) n FROM alerts').fetchone()['n']
        user_count=db.execute('SELECT COUNT(*) n FROM users').fetchone()['n']
    chronological=list(reversed(readings))
    source=latest['data_source'] if latest else 'SIMULATED'
    return render_template_string(DASHBOARD, username=session['username'], role=session['role'], today=datetime.now().strftime('%A, %d %B %Y'), latest=latest, readings=readings, alerts=alerts, data_mode=('SIMULATED' if source in ('SIMULATED','DEMO') else ('HARDWARE' if latest and _age_seconds(latest['recorded_at'])<=DEVICE_TIMEOUT_S else 'STALE')), user_count=user_count,total_readings=total_readings,total_alerts=total_alerts, chart_labels=[r['recorded_at'][11:16] for r in chronological], chart_temps=[r['temperature'] for r in chronological], chart_hums=[r['humidity'] for r in chronological], chart_statuses=[r['status'] for r in chronological])

@app.route('/simulate/normal',methods=['POST'])
@login_required
def generate_normal():
    save_reading(round(random.uniform(24,30),1),round(random.uniform(50,70),1),random.randint(600,1400),'SIMULATED')
    return redirect(url_for('dashboard'))

@app.route('/simulate/abnormal',methods=['POST'])
@login_required
def generate_abnormal():
    save_reading(round(random.uniform(34,38),1),round(random.uniform(50,70),1),random.randint(2300,3200),'SIMULATED')
    return redirect(url_for('dashboard'))

def _num(payload, key, lo, hi):
    v = payload.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)): raise ValueError(f'{key} must be a number')
    v = float(v)
    if not (lo <= v <= hi) or v != v: raise ValueError(f'{key} out of range {lo}..{hi}')
    return v

@app.route('/api/readings', methods=['POST'])
def api_readings():
    """ESP32 -> backend. Header X-API-Key, JSON {device_id, temperature, humidity, gas_raw}."""
    if request.headers.get('X-API-Key','') != DEVICE_API_KEY:
        return jsonify(error='invalid device key'), 401
    p = request.get_json(silent=True)
    if not isinstance(p, dict): return jsonify(error='JSON body required'), 400
    try:
        t = _num(p,'temperature',-40,80); h = _num(p,'humidity',0,100); g = int(_num(p,'gas_raw',0,4095))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    device = str(p.get('device_id','esp32'))[:40]
    source = 'SIMULATED' if device.lower().startswith('sim') else 'ESP32'   # honest labelling
    status, warnings = save_reading(t, h, g, source=source, device_id=device)
    return jsonify(status=status, warnings=warnings), 201

@app.route('/api/latest')
@login_required
def api_latest():
    with connect_db() as db: r = db.execute('SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 1').fetchone()
    if not r: return jsonify(id=0)
    return jsonify(id=r['id'], temperature=r['temperature'], humidity=r['humidity'], gas_raw=r['gas_value'],
                   status=r['status'], source=r['data_source'], risk_prob=r['risk_prob'],
                   recorded_at=r['recorded_at'], online=_age_seconds(r['recorded_at'])<=DEVICE_TIMEOUT_S)

@app.route('/api/test-sms', methods=['POST'])
@login_required
def api_test_sms():
    st, det = sms.send_sms('SMART-POULTRY test message: SMS alerts are working.')
    return jsonify(status=st, detail=det)

@app.route('/api/assistant',methods=['POST'])
@login_required
def assistant_api():
    data=request.get_json(silent=True) or {}; q=str(data.get('question','')).strip()[:700]
    if not q: return jsonify(error='Please enter a question.'),400
    low=q.lower()
    with connect_db() as db:
        latest=db.execute('SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 1').fetchone()
        alerts=db.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT 5').fetchall()
        count=db.execute('SELECT COUNT(*) n FROM sensor_readings').fetchone()['n']
    if any(w in low for w in ('summar','latest','current reading','dashboard')):
        if not latest: answer='There are no saved readings yet. Generate a simulated test reading or connect a verified sensor first.'
        else:
            warnings=analyse_reading(latest['temperature'],latest['humidity'],latest['gas_value'])
            answer=(f"Latest saved reading ({latest['data_source']}, {latest['recorded_at']}): temperature {latest['temperature']:.1f} °C, relative humidity {latest['humidity']:.1f}%, gas raw signal {latest['gas_value']}, status {latest['status']}. " + ('Items to investigate: '+' '.join(warnings) if warnings else 'No configured prototype threshold was exceeded. This is not a guarantee of flock health.'))
    elif 'gas' in low or 'ammonia' in low or 'smell' in low:
        answer='The dashboard gas value is a raw MQ-series sensor signal, not a calibrated gas concentration or ppm reading. Confirm whether the reading is simulated, check sensor warm-up, wiring and ventilation, and use a suitable calibrated instrument if gas concentration must be measured. Increase ventilation only in a way that maintains appropriate temperature and avoids drafts; if birds show distress, seek qualified poultry/veterinary help.'
        if latest: answer+=f" Latest saved raw signal: {latest['gas_value']} ({latest['data_source']})."
    elif any(w in low for w in ('temperature','hot','heat','warm')):
        answer='First verify the value, sensor placement and whether the data is simulated. Check flock age, bird distribution and behaviour, water availability, ventilation and actual house conditions. The dashboard 18–32 °C range is an illustrative software threshold, not a universal target for every flock age. If birds are panting, collapsing or otherwise distressed, contact a poultry veterinarian and follow established farm emergency procedures.'
        if latest: answer+=f" Latest saved temperature: {latest['temperature']:.1f} °C ({latest['data_source']})."
    elif any(w in low for w in ('humidity','moist','wet litter')):
        answer='Verify the humidity sensor and inspect litter condition, drinker leaks, airflow and condensation. Interpret humidity together with flock age, temperature and ventilation; the dashboard 40–75% range is configurable demonstration logic, not a validated universal husbandry standard.'
        if latest: answer+=f" Latest saved humidity: {latest['humidity']:.1f}% ({latest['data_source']})."
    elif any(w in low for w in ('alert','warning','abnormal','risk')):
        answer='A warning means a reading crossed one or more configured software thresholds; it is a prompt to investigate, not a diagnosis. Verify the reading and its source, inspect sensor placement and compare with the flock’s behaviour and farm records.'
        if alerts: answer+=' Recent alert: '+alerts[0]['message']
        else: answer+=' There are no stored alerts at present.'
    elif any(w in low for w in ('disease','sick','mortality','dying','symptom','diagnos')):
        answer='I cannot diagnose poultry disease from environmental readings. Record the signs, timing, age and number of affected birds, check feed and water access and environmental conditions, and contact a qualified poultry veterinarian promptly—especially for unusual mortality, rapid spread or severe distress.'
    elif any(w in low for w in ('limitation','data','simulat','hardware','sensor','real')):
        answer=f"There are {count} stored readings. Each record's source column indicates SIMULATED or the source name saved by the application. Do not describe simulated readings as physical measurements. Hardware data should only be labelled as such after the sensor-to-dashboard path has been tested." 
    else:
        answer='I can help explain saved readings, temperature/humidity/gas-signal warnings, sensor-data limitations and sensible next checks. Tell me the value and unit, whether it is simulated or measured, flock age and what you observed. For disease concerns, severe distress or unusual mortality, consult a qualified poultry veterinarian.'
    with connect_db() as db: db.execute('INSERT INTO chat_messages(username,role,message,response,recorded_at) VALUES(?,?,?,?,?)',(session['username'],session['role'],q,answer,now_text()))
    return jsonify(response=answer,mode='local-rule-based')

@app.route('/export.csv')
@login_required
def export_csv():
    from io import StringIO
    import csv
    out=StringIO(); writer=csv.writer(out); writer.writerow(['recorded_at','temperature_c','relative_humidity_percent','gas_raw_signal','data_source','status'])
    with connect_db() as db: rows=db.execute('SELECT recorded_at,temperature,humidity,gas_value,data_source,status FROM sensor_readings ORDER BY id DESC').fetchall()
    writer.writerows([tuple(r) for r in rows])
    from flask import Response
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=smart_poultry_readings.csv'})

@app.route('/manifest.webmanifest')
def manifest():
    return jsonify({'name':'SMART-Poultry Monitoring','short_name':'SMART-Poultry','start_url':'/','display':'standalone','background_color':'#07141d','theme_color':'#071721','description':'Environmental monitoring and early-warning prototype','icons':[{'src':'/static/icon.svg','sizes':'any','type':'image/svg+xml','purpose':'any maskable'}]})

@app.route('/service-worker.js')
def service_worker():
    return send_from_directory(BASE_DIR/'static','service-worker.js',mimetype='application/javascript')

@app.after_request
def security_headers(response):
    response.headers.setdefault('X-Content-Type-Options','nosniff')
    response.headers.setdefault('X-Frame-Options','SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy','strict-origin-when-cross-origin')
    return response

ai.load_models()
init_db()
if __name__=='__main__':
    print('AI model :', ai.load_models())
    print('SMS      :', 'configured' if (config.SMS_ENABLED and config.SMS_API_KEY and config.SMS_RECIPIENTS) else 'NOT configured (alerts still logged)')
    app.run(host='0.0.0.0', port=5000, debug=False)   # 0.0.0.0 so the ESP32 can reach it
