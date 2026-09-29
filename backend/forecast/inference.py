from __future__ import annotations

import hashlib
from functools import lru_cache

import numpy as np
import onnxruntime as ort

from .config import MANIFEST_PATH, MODEL_PATH, SCALER_PATH, read_json


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_assets() -> dict:
    manifest = read_json(MANIFEST_PATH)
    for relative_path, expected in manifest["artifacts_sha256"].items():
        path = MANIFEST_PATH.parent / relative_path
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"Artifact validation failed: {relative_path}")
    return manifest


@lru_cache(maxsize=1)
def get_session() -> ort.InferenceSession:
    return ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])


def predict(scaled_features: np.ndarray) -> np.ndarray:
    if scaled_features.shape != (168, 15) or not np.isfinite(scaled_features).all():
        raise ValueError("Inference input must be finite with shape (168, 15).")
    session = get_session()
    input_name = session.get_inputs()[0].name
    output = session.run(None, {input_name: scaled_features[None, :, :]})[0]
    if output.shape != (1, 24) or not np.isfinite(output).all():
        raise RuntimeError("ONNX output violates the (1, 24) contract.")
    scaler = read_json(SCALER_PATH)["y_scaler"]
    result = output[0].astype(np.float64) * float(scaler["scale"][0]) + float(
        scaler["center"][0]
    )
    if not np.isfinite(result).all():
        raise RuntimeError("Inverse-scaled prediction contains nonfinite values.")
    return result
