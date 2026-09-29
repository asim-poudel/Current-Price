"""Build the small, TensorFlow-free artifact bundle used by production."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import keras
import numpy as np
import onnxruntime as ort
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "backend" / "assets"
FEATURES = json.loads((ROOT / "models" / "cnn_lstm_config.json").read_text())["features_cols"]
ORIGIN = datetime(2024, 8, 31, 12, tzinfo=timezone.utc)


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def records(path: Path, start: datetime, end: datetime) -> list[dict]:
    frame = pq.read_table(path).to_pandas()
    frame = frame[(frame.index >= start) & (frame.index < end)]
    return [
        {
            "timestamp_utc": index.isoformat().replace("+00:00", "Z"),
            **{column: float(row[column]) for column in frame.columns},
        }
        for index, row in frame.iterrows()
    ]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "rag").mkdir(exist_ok=True)

    x_scaler = joblib.load(ROOT / "models" / "X_scaler.joblib")
    y_scaler = joblib.load(ROOT / "models" / "y_scaler.joblib")
    scaler = {
        "schema_version": "1.0",
        "feature_order": FEATURES,
        "x_scaler": {"type": "StandardScaler", "mean": x_scaler.mean_.tolist(), "scale": x_scaler.scale_.tolist()},
        "y_scaler": {"type": "RobustScaler", "center": y_scaler.center_.tolist(), "scale": y_scaler.scale_.tolist()},
    }
    dump(ASSETS / "scaler_parameters.json", scaler)
    shutil.copy2(ROOT / "models" / "cnn_lstm_config.json", ASSETS / "cnn_lstm_config.json")
    for source in (ROOT / "rag_assets").iterdir():
        if source.is_file():
            shutil.copy2(source, ASSETS / "rag" / source.name)

    model = keras.models.load_model(ROOT / "models" / "best_cnn_lstm.keras", compile=False)
    if tuple(model.input_shape) != (None, 168, 15) or tuple(model.output_shape) != (None, 24):
        raise RuntimeError("Unexpected frozen model shape.")
    onnx_path = ASSETS / "best_cnn_lstm.onnx"
    model.export(
        onnx_path,
        format="onnx",
        input_signature=[keras.InputSpec(shape=(1, 168, 15), dtype="float32", name="features")],
        opset_version=18,
    )

    feature_rows = records(
        ROOT / "data" / "processed" / "smard_features.parquet",
        ORIGIN - timedelta(hours=168),
        ORIGIN,
    )
    raw_input = np.asarray([[row[name] for name in FEATURES] for row in feature_rows], dtype=np.float64)
    scaled = ((raw_input - x_scaler.mean_) / x_scaler.scale_).astype(np.float32)
    keras_scaled = np.asarray(model.predict(scaled[None, :, :], verbose=0), dtype=np.float32)
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    onnx_scaled = session.run(None, {session.get_inputs()[0].name: scaled[None, :, :]})[0]
    np.testing.assert_allclose(onnx_scaled, keras_scaled, rtol=1e-4, atol=1e-4)
    keras_prices = y_scaler.inverse_transform(keras_scaled.reshape(-1, 1)).ravel()
    onnx_prices = y_scaler.inverse_transform(onnx_scaled.reshape(-1, 1)).ravel()
    if float(np.max(np.abs(keras_prices - onnx_prices))) >= 0.01:
        raise RuntimeError("ONNX price parity exceeded 0.01 EUR/MWh.")

    dump(
        ASSETS / "smoke_test.json",
        {
            "schema_version": "1.0",
            "origin_utc": ORIGIN.isoformat().replace("+00:00", "Z"),
            "feature_order": FEATURES,
            "scaled_input": scaled.tolist(),
            "expected_scaled_output": keras_scaled[0].tolist(),
            "expected_price_eur_mwh": keras_prices.tolist(),
        },
    )
    fixture = {
        "origin_utc": ORIGIN.isoformat().replace("+00:00", "Z"),
        "observations": records(
            ROOT / "data" / "processed" / "smard_hourly_clean.parquet",
            ORIGIN - timedelta(hours=336),
            ORIGIN,
        ),
        "expected_features": raw_input.tolist(),
    }
    fixtures = ROOT / "backend" / "tests" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    dump(fixtures / "feature_parity.json", fixture)

    artifacts = [
        "best_cnn_lstm.onnx",
        "cnn_lstm_config.json",
        "scaler_parameters.json",
        "smoke_test.json",
        "rag/rag_config.json",
        "rag/rag_manifest.json",
        "rag/rag_system_rules.txt",
        "rag/static_chunks.json",
        "rag/static_embeddings.npy",
        "rag/static_index_metadata.json",
    ]
    dump(
        ASSETS / "production_manifest.json",
        {
            "schema_version": "1.0",
            "model_version": "cnn_lstm_v1_frozen",
            "onnx_opset": 18,
            "input_shape": [1, 168, 15],
            "output_shape": [1, 24],
            "artifacts_sha256": {name: sha256(ASSETS / name) for name in artifacts},
        },
    )
    print(f"Exported {onnx_path} ({onnx_path.stat().st_size / 1024 / 1024:.2f} MiB)")
    print(f"Maximum Keras/ONNX price difference: {np.max(np.abs(keras_prices - onnx_prices)):.8f} EUR/MWh")


if __name__ == "__main__":
    main()
