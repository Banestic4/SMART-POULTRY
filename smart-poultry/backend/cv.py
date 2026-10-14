"""Image feature extraction (identical to ml/train_cv.py - keep the two in sync)."""
import numpy as np

SIZE = 128


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
