"""AI layer: environmental risk model + image classifier (both optional at start-up)."""
import os

import joblib
import numpy as np

import config

_env = None
_cv = None


def _load(name):
    path = os.path.join(config.MODEL_DIR, name)
    return joblib.load(path) if os.path.exists(path) else None


def load_models():
    global _env, _cv
    _env = _load("env_model.joblib")
    _cv = _load("cv_model.joblib")
    return {"env": _env["name"] if _env else None, "cv": bool(_cv)}


def predict_environment(temperature, humidity, gas_pct):
    """Return (probability_at_risk, label) or (None, None) if the model is not trained."""
    if _env is None:
        return None, None
    x = np.array([[temperature, humidity, gas_pct]])
    p = float(_env["model"].predict_proba(x)[0][1])
    return round(p, 4), ("At-risk" if p >= config.ML_RISK_THRESHOLD else "Normal")


def cv_available():
    return _cv is not None


def classify_image(pil_image):
    """Return (class_name, confidence) using the classical-CV model."""
    if _cv is None:
        return None, None
    from cv import extract_features
    f = extract_features(pil_image).reshape(1, -1)
    proba = _cv["model"].predict_proba(f)[0]
    i = int(np.argmax(proba))
    return _cv["classes"][i], round(float(proba[i]), 4)
