"""SMART-Poultry configuration.

Every value can be overridden with an environment variable, so secrets
(API keys, passwords) never have to be written into the source code.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _f(name, default):
    return float(os.environ.get(name, default))


def _i(name, default):
    return int(os.environ.get(name, default))


# ---- Core -----------------------------------------------------------------
SECRET_KEY = os.environ.get("SP_SECRET_KEY", "change-this-secret-before-deployment")
DB_PATH = os.environ.get("SP_DB_PATH", os.path.join(BASE_DIR, "smartpoultry.db"))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
MODEL_DIR = os.path.join(BASE_DIR, "models")

# Shared secret the ESP32 sends in the X-API-Key header.
DEVICE_API_KEY = os.environ.get("SP_DEVICE_API_KEY", "sp-device-key-123")

# ---- Alert thresholds (poultry-house operating range) ----------------------
# Adjust to the age of the birds and to the references cited in Chapter Two.
TEMP_HIGH = _f("SP_TEMP_HIGH", 32.0)      # deg C  -> heat-stress alert
TEMP_LOW = _f("SP_TEMP_LOW", 18.0)        # deg C  -> cold-stress alert
HUM_HIGH = _f("SP_HUM_HIGH", 75.0)        # % RH
HUM_LOW = _f("SP_HUM_LOW", 40.0)          # % RH
# MQ135 is read as a 12-bit ADC value (0-4095). Calibrate in clean air first and
# set the threshold above that baseline (see README, "Calibrating the MQ135").
GAS_HIGH_RAW = _i("SP_GAS_HIGH_RAW", 2200)

# ML risk probability above which a "predicted risk" alert is raised.
ML_RISK_THRESHOLD = _f("SP_ML_RISK_THRESHOLD", 0.70)

# A reading older than this (seconds) marks the device as OFFLINE on the dashboard.
DEVICE_TIMEOUT_S = _i("SP_DEVICE_TIMEOUT_S", 30)

# ---- SMS (Termii by default) ------------------------------------------------
SMS_ENABLED = os.environ.get("SP_SMS_ENABLED", "1") == "1"
SMS_PROVIDER = os.environ.get("SP_SMS_PROVIDER", "termii")
SMS_API_KEY = os.environ.get("SP_SMS_API_KEY", "")
# Termii shows your account-specific base URL on the dashboard, e.g. https://api.ng.termii.com
SMS_BASE_URL = os.environ.get("SP_SMS_BASE_URL", "https://api.ng.termii.com")
SMS_SENDER_ID = os.environ.get("SP_SMS_SENDER_ID", "SMARTPOULTRY")
# International format without '+', e.g. 2348012345678. Several numbers: comma separated.
SMS_RECIPIENTS = [n.strip() for n in os.environ.get("SP_SMS_RECIPIENTS", "").split(",") if n.strip()]
# 'dnd' reaches all numbers (must be activated on the account); 'generic' is promotional only.
SMS_CHANNEL = os.environ.get("SP_SMS_CHANNEL", "dnd")
# Minimum seconds between two SMS of the same alert type (protects SMS credit).
SMS_COOLDOWN_S = _i("SP_SMS_COOLDOWN_S", 300)

# ---- Login protection -------------------------------------------------------
MAX_LOGIN_ATTEMPTS = _i("SP_MAX_LOGIN_ATTEMPTS", 5)
LOCKOUT_SECONDS = _i("SP_LOCKOUT_SECONDS", 300)
