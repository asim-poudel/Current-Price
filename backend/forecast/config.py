from __future__ import annotations

import json
import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = BACKEND_ROOT / "assets"
RAG_ASSET_DIR = ASSET_DIR / "rag"

MODEL_PATH = ASSET_DIR / "best_cnn_lstm.onnx"
MODEL_CONFIG_PATH = ASSET_DIR / "cnn_lstm_config.json"
SCALER_PATH = ASSET_DIR / "scaler_parameters.json"
MANIFEST_PATH = ASSET_DIR / "production_manifest.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def allowed_origins() -> list[str]:
    value = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )
    return [origin.strip() for origin in value.split(",") if origin.strip()]
