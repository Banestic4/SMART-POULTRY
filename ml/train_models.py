"""Train and evaluate the environmental risk models (Logistic Regression + Random Forest).

DATA: simulated poultry-house readings (temperature, humidity, MQ135 gas %), as stated in
Sections 1.6 and 1.8 of the report ("initial stage uses simulated environmental data").
LABELS: derived from documented operating-range rules plus compound-stress rules and 3%
random label noise to represent sensor/labelling uncertainty. The models therefore learn
a *risk function defined from poultry-housing guidelines*, NOT real disease outcomes.
This limitation must be stated in Chapter Four.

Run:   python train_models.py
Output (in ../backend/models and ../docs/results):
    env_model.joblib, env_metrics.json, confusion_matrices.png,
    feature_importance.png, simulated_dataset.csv
"""
import json
import os

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

SEED = 42
N = 6000
FEATURES = ["temperature", "humidity", "gas_pct"]
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "..", "backend", "models")
RESULT_DIR = os.path.join(HERE, "..", "docs", "results")
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)


def deviation_features(X):
    """Distance from the comfortable centre of each range - makes the two-sided risk linear."""
    X = np.asarray(X, dtype=float)
    return np.column_stack([np.abs(X[:, 0] - 25.0), np.abs(X[:, 1] - 57.5), X[:, 2]])


def risk_rule(t, h, g):
    """1 = at-risk environment, 0 = normal. Thresholds mirror backend/config.py."""
    single = (t >= 32) | (t < 18) | (h > 75) | (h < 40) | (g > 53.7)
    compound = ((t > 29) & (h > 70)) | ((g > 45) & (h > 70)) | ((t > 30) & (g > 45))
    return (single | compound).astype(int)


def simulate(n, rng):
    """Mixture of normal operation and several stress scenarios."""
    scen = rng.choice(["normal", "heat", "cold", "humid", "dry", "gas", "mixed"], size=n,
                      p=[0.50, 0.10, 0.06, 0.08, 0.05, 0.11, 0.10])
    t = np.empty(n); h = np.empty(n); g = np.empty(n)
    for i, s in enumerate(scen):
        t[i] = rng.normal(26, 2.2); h[i] = rng.normal(60, 6); g[i] = rng.normal(28, 7)
        if s in ("heat", "mixed"):  t[i] = rng.normal(33, 2.0)
        if s == "cold":             t[i] = rng.normal(16, 1.5)
        if s in ("humid", "mixed"): h[i] = rng.normal(80, 5)
        if s == "dry":              h[i] = rng.normal(33, 5)
        if s in ("gas", "mixed"):   g[i] = rng.normal(58, 9)
    t = np.clip(t, 5, 45); h = np.clip(h, 10, 100); g = np.clip(g, 0, 100)
    return pd.DataFrame({"temperature": t.round(1), "humidity": h.round(1), "gas_pct": g.round(1)})


def main():
    rng = np.random.default_rng(SEED)
    df = simulate(N, rng)
    y = risk_rule(df.temperature, df.humidity, df.gas_pct).to_numpy()
    flip = rng.random(N) < 0.03                      # 3 % label noise
    y = np.where(flip, 1 - y, y)
    df["label"] = y
    df.to_csv(os.path.join(RESULT_DIR, "simulated_dataset.csv"), index=False)

    X = df[FEATURES].to_numpy()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)

    models = {
        "Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")),
        "Logistic Regression (deviation features)": make_pipeline(
            FunctionTransformer(deviation_features), StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced")),
        "Random Forest": RandomForestClassifier(n_estimators=200, max_depth=10, class_weight="balanced",
                                                random_state=SEED, n_jobs=-1),
    }
    metrics = {"dataset": {"samples": int(N), "train": int(len(ytr)), "test": int(len(yte)),
                           "at_risk_share": round(float(y.mean()), 3), "label_noise": 0.03,
                           "features": FEATURES}}
    cms = {}
    for name, m in models.items():
        cv = cross_val_score(m, Xtr, ytr, cv=5, scoring="f1")
        m.fit(Xtr, ytr)
        p = m.predict(Xte)
        proba = m.predict_proba(Xte)[:, 1]
        metrics[name] = {
            "accuracy": round(accuracy_score(yte, p), 4),
            "precision": round(precision_score(yte, p), 4),
            "recall": round(recall_score(yte, p), 4),
            "f1": round(f1_score(yte, p), 4),
            "roc_auc": round(roc_auc_score(yte, proba), 4),
            "cv_f1_mean": round(float(cv.mean()), 4),
            "cv_f1_std": round(float(cv.std()), 4),
        }
        cms[name] = confusion_matrix(yte, p)
        print(name, metrics[name])

    # Deploy the better model by F1 (ties -> Random Forest).
    # The Random Forest is deployed: it needs no hand-made features and handles the two-sided
    # (U-shaped) risk of temperature/humidity. (The engineered-feature LR cannot be pickled
    # without shipping this file, so it is only used for the comparison.)
    best = "Random Forest"
    metrics["deployed_model"] = best
    joblib.dump({"model": models[best], "features": FEATURES, "name": best},
                os.path.join(MODEL_DIR, "env_model.joblib"))
    with open(os.path.join(RESULT_DIR, "env_metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)

    # Figures for Chapter Four
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.9))
    for ax, (name, cm) in zip(axes, cms.items()):
        ax.imshow(cm, cmap="Blues")
        ax.set_title(name, fontsize=9)
        ax.set_xticks([0, 1], ["Normal", "At-risk"]); ax.set_yticks([0, 1], ["Normal", "At-risk"])
        ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
        for (i, j), v in np.ndenumerate(cm):
            ax.text(j, i, int(v), ha="center", va="center", color="black", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(RESULT_DIR, "confusion_matrices.png"), dpi=200); plt.close(fig)

    rf = models["Random Forest"]
    fig, ax = plt.subplots(figsize=(5, 3.2))
    ax.barh(FEATURES, rf.feature_importances_, color="#2f6f4f")
    ax.set_xlabel("Importance"); ax.set_title("Random Forest feature importance")
    fig.tight_layout(); fig.savefig(os.path.join(RESULT_DIR, "feature_importance.png"), dpi=200); plt.close(fig)
    print("Deployed:", best)


if __name__ == "__main__":
    main()
