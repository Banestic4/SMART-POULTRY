"""Train the poultry image classifier (computer-vision module).

You must supply a labelled image dataset (not included, no dataset could be downloaded
while building this project). Expected layout:

    ml/dataset/
        healthy/        *.jpg
        coccidiosis/    *.jpg
        newcastle/      *.jpg
        salmonella/     *.jpg
(the folder names ARE the class labels - use whatever classes your dataset has)

Method: classical computer vision. Each image is resized to 128x128, then described by
  - an HSV colour histogram (8x4x4 bins), and
  - a gradient-orientation histogram (texture/edges, 9 bins) on the grey image,
  - mean/std of each RGB channel,
and classified with a Random Forest. Only Pillow, NumPy and scikit-learn are needed.

IMPORTANT for the report: this is feature-based machine learning, not a CNN. Chapter 1/3 say
"CNN or transfer learning" - either train a CNN on Google Colab and report it instead, or
amend those sentences to describe this method.

Run:  python train_cv.py [dataset_dir]
"""
import json
import os
import sys

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "..", "backend", "models")
RESULT_DIR = os.path.join(HERE, "..", "docs", "results")
EXTS = (".jpg", ".jpeg", ".png", ".bmp")
SIZE = 128
MAX_PER_CLASS = 1500   # keeps training fast on a modest laptop


def extract_features(img):
    """Shared by training and by the Flask backend (backend/cv.py has the same function)."""
    img = img.convert("RGB").resize((SIZE, SIZE))
    arr = np.asarray(img, dtype=np.float32)
    hsv = np.asarray(img.convert("HSV"), dtype=np.float32)
    hist, _ = np.histogramdd(hsv.reshape(-1, 3), bins=(8, 4, 4), range=((0, 256), (0, 256), (0, 256)))
    hist = (hist / hist.sum()).ravel()
    grey = arr.mean(axis=2)
    gy, gx = np.gradient(grey)
    mag = np.hypot(gx, gy)
    ang = (np.arctan2(gy, gx) % np.pi)
    ohist, _ = np.histogram(ang, bins=9, range=(0, np.pi), weights=mag)
    ohist = ohist / (ohist.sum() + 1e-9)
    stats = np.concatenate([arr.mean(axis=(0, 1)) / 255, arr.std(axis=(0, 1)) / 255])
    return np.concatenate([hist, ohist, stats]).astype(np.float32)


def load_dataset(root):
    classes = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    X, y = [], []
    rng = np.random.default_rng(42)
    for ci, c in enumerate(classes):
        files = [f for f in os.listdir(os.path.join(root, c)) if f.lower().endswith(EXTS)]
        rng.shuffle(files)
        for f in files[:MAX_PER_CLASS]:
            try:
                X.append(extract_features(Image.open(os.path.join(root, c, f))))
                y.append(ci)
            except Exception as exc:  # corrupt image
                print("skip", f, exc)
        print(f"{c}: {min(len(files), MAX_PER_CLASS)} images")
    return np.array(X), np.array(y), classes


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "dataset")
    if not os.path.isdir(root):
        sys.exit(f"Dataset folder not found: {root}")
    os.makedirs(MODEL_DIR, exist_ok=True); os.makedirs(RESULT_DIR, exist_ok=True)
    X, y, classes = load_dataset(root)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    clf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=42, n_jobs=-1)
    clf.fit(Xtr, ytr)
    pred = clf.predict(Xte)
    rep = classification_report(yte, pred, target_names=classes, output_dict=True, zero_division=0)
    print(classification_report(yte, pred, target_names=classes, zero_division=0))
    with open(os.path.join(RESULT_DIR, "cv_metrics.json"), "w") as fh:
        json.dump({"classes": classes, "train": int(len(ytr)), "test": int(len(yte)), "report": rep}, fh, indent=2)
    cm = confusion_matrix(yte, pred)
    fig, ax = plt.subplots(figsize=(5.5, 4.8))
    ax.imshow(cm, cmap="Greens")
    ax.set_xticks(range(len(classes)), classes, rotation=30, ha="right"); ax.set_yticks(range(len(classes)), classes)
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual"); ax.set_title("Image classifier confusion matrix")
    for (i, j), v in np.ndenumerate(cm):
        ax.text(j, i, int(v), ha="center", va="center")
    fig.tight_layout(); fig.savefig(os.path.join(RESULT_DIR, "cv_confusion_matrix.png"), dpi=200)
    joblib.dump({"model": clf, "classes": classes}, os.path.join(MODEL_DIR, "cv_model.joblib"))
    print("Saved backend/models/cv_model.joblib")


if __name__ == "__main__":
    main()
