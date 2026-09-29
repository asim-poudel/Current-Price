from __future__ import annotations

import json
import re
from functools import lru_cache

import numpy as np
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .config import RAG_ASSET_DIR, required_env


PROJECT_SCOPE_TERMS = {
    "electricity", "price", "forecast", "forecasting", "model", "cnn", "lstm",
    "architecture", "feature", "lookback", "horizon", "load", "mae", "rmse",
    "smape", "mape", "error", "actual", "prediction", "metric", "training",
    "validation", "test", "historical", "yesterday", "today", "latest",
}
DYNAMIC_PHRASES = {
    "today", "tomorrow", "yesterday", "latest forecast", "current forecast",
    "previous forecast", "last forecast", "latest prediction", "current prediction",
    "previous day", "last day", "live metric", "latest metric", "current metric",
}
STATIC_TERMS = {
    "architecture", "feature", "lookback", "horizon", "training", "validation",
    "historical", "limitation", "definition", "conv1d", "dropout", "scaler",
    "why", "explain", "meaning", "interpret", "compare",
}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was",
    "what", "when", "where", "which", "with",
}
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")


class GroundedAnswer(BaseModel):
    answer: str = Field(description="A concise answer supported only by supplied evidence.")
    source_ids: list[str]
    data_status: str


def classify_question(question: str) -> str:
    normalized = question.lower().strip()
    if not normalized or not any(term in normalized for term in PROJECT_SCOPE_TERMS):
        return "unsupported"
    dynamic = any(phrase in normalized for phrase in DYNAMIC_PHRASES)
    static = any(term in normalized for term in STATIC_TERMS)
    if dynamic and static:
        return "mixed"
    return "dynamic" if dynamic else "static"


def _metric_names(question: str) -> list[str]:
    normalized = question.lower()
    requested = [name for name in ("mae", "rmse", "smape") if re.search(rf"\b{name}\b", normalized)]
    if re.search(r"\bmape\b", re.sub(r"\bsmape\b", "", normalized)):
        requested.append("mape")
    if any(phrase in normalized for phrase in ("all metrics", "error metrics", "error rates")):
        requested = ["mae", "rmse", "smape", "mape"]
    return list(dict.fromkeys(requested))


def deterministic_dynamic_answer(question: str, payload: dict | None) -> dict | None:
    metrics_requested = _metric_names(question)
    asks_worst = any(phrase in question.lower() for phrase in ("worst hour", "largest error", "biggest error"))
    if not metrics_requested and not asks_worst:
        return None
    if not payload:
        return _response("Current operational evaluation data is not available.", [], "unavailable", "dynamic")
    if payload["status"] == "pending":
        return _response(payload["message"], ["dynamic:previous_evaluation"], "pending", "dynamic")
    labels = {
        "mae": ("mae_eur_mwh", "MAE", "EUR/MWh"),
        "rmse": ("rmse_eur_mwh", "RMSE", "EUR/MWh"),
        "smape": ("smape_pct", "sMAPE", "%"),
        "mape": ("mape_guarded_pct", "guarded MAPE", "%"),
    }
    parts = []
    for name in metrics_requested:
        field, label, unit = labels[name]
        value = payload["metrics"].get(field)
        parts.append(f"{label}: {value:.3f} {unit}" if value is not None else f"{label}: unavailable")
    if asks_worst and payload.get("worst_hour"):
        worst = payload["worst_hour"]
        parts.append(
            "largest absolute error: "
            f"{worst['absolute_error_eur_mwh']:.3f} EUR/MWh at {worst['delivery_time_utc']}"
        )
    answer = f"For the forecast issued at {payload['forecast_origin_utc']}, " + "; ".join(parts) + "."
    if "mape" in metrics_requested:
        answer += f" Guarded MAPE excluded {payload['metrics']['mape_excluded_hours']} hour(s)."
    return _response(answer, ["dynamic:previous_evaluation"], "complete", "dynamic")


def _response(answer: str, source_ids: list[str], data_status: str, route: str) -> dict:
    return {"schema_version": "1.0", "answer": answer, "source_ids": source_ids, "data_status": data_status, "route": route}


@lru_cache(maxsize=1)
def _static_index() -> tuple[np.ndarray, list[dict], dict, str]:
    embeddings = np.load(RAG_ASSET_DIR / "static_embeddings.npy", allow_pickle=False).astype(np.float32)
    chunks = json.loads((RAG_ASSET_DIR / "static_chunks.json").read_text(encoding="utf-8"))
    config = json.loads((RAG_ASSET_DIR / "rag_config.json").read_text(encoding="utf-8"))
    rules = (RAG_ASSET_DIR / "rag_system_rules.txt").read_text(encoding="utf-8")
    if embeddings.shape != (len(chunks), config["embedding_dimension"]):
        raise RuntimeError("Static RAG assets do not match their metadata.")
    return embeddings, chunks, config, rules


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    return genai.Client(api_key=required_env("GEMINI_API_KEY"))


def _normalize(vector) -> np.ndarray:
    result = np.asarray(vector, dtype=np.float32)
    magnitude = np.linalg.norm(result)
    if not np.isfinite(magnitude) or magnitude == 0:
        raise RuntimeError("Gemini returned an invalid embedding.")
    return result / magnitude


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if token not in STOPWORDS}


def retrieve_static(question: str) -> list[dict]:
    embeddings, chunks, config, _ = _static_index()
    instruction = (
        "Task: retrieve authoritative electricity-price forecasting documentation. "
        f"Input type: retrieval_query.\n\n{question}"
    )
    result = _client().models.embed_content(
        model=config["embedding_model"],
        contents=instruction,
        config=types.EmbedContentConfig(output_dimensionality=config["embedding_dimension"]),
    )
    query = _normalize(result.embeddings[0].values)
    semantic = embeddings @ query
    question_tokens = _tokens(question)
    scored = []
    for index, chunk in enumerate(chunks):
        lexical = len(question_tokens & _tokens(chunk["text"])) / len(question_tokens) if question_tokens else 0.0
        scored.append({**chunk, "score": 0.85 * float(semantic[index]) + 0.15 * lexical})
    return sorted(scored, key=lambda item: item["score"], reverse=True)[: config["top_k"]]


def _dynamic_block(payload: dict) -> dict:
    compact = {
        key: payload.get(key)
        for key in (
            "schema_version", "data_class", "is_live", "status", "model_version",
            "forecast_origin_utc", "available_actual_hours", "metrics", "worst_hour", "message",
        )
    }
    return {
        "source_id": "dynamic:previous_evaluation",
        "title": "Previous scheduled forecast evaluation",
        "text": json.dumps(compact, indent=2, allow_nan=False),
    }


def _has_unsupported_numbers(answer: str, question: str, blocks: list[dict]) -> bool:
    evidence = question + " " + " ".join(block["text"] for block in blocks)
    evidence_numbers = [float(match.group(0)) for match in NUMBER_PATTERN.finditer(evidence)]
    return any(
        not any(np.isclose(float(match.group(0)), value, rtol=5e-3, atol=5e-3) for value in evidence_numbers)
        for match in NUMBER_PATTERN.finditer(answer)
    )


def _generate(question: str, blocks: list[dict], data_status: str) -> dict:
    _, _, config, rules = _static_index()
    ids = [block["source_id"] for block in blocks]
    evidence = "\n\n---\n\n".join(
        f"EVIDENCE_ID: {block['source_id']}\nTITLE: {block['title']}\nCONTENT:\n{block['text']}"
        for block in blocks
    )
    prompt = f"{rules}\n\nAVAILABLE_SOURCE_IDS:\n{json.dumps(ids)}\n\nUSER_QUESTION:\n{question}\n\nEVIDENCE:\n{evidence}"
    result = _client().models.generate_content(
        model=config["generation_model"],
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GroundedAnswer,
            temperature=0,
        ),
    )
    parsed = GroundedAnswer.model_validate_json(result.text)
    if not parsed.source_ids or set(parsed.source_ids) - set(ids):
        return _response("The requested information is unavailable in the supplied project evidence.", [], "insufficient_evidence", "static")
    if _has_unsupported_numbers(parsed.answer, question, blocks):
        return _response("The generated answer contained an unsupported numeric claim, so it was blocked.", [], "insufficient_evidence", "static")
    return {"schema_version": "1.0", "answer": parsed.answer.strip(), "source_ids": parsed.source_ids, "data_status": data_status}


def answer_question(question: str, dynamic_payload: dict | None) -> dict:
    route = classify_question(question)
    if route == "unsupported":
        return _response(
            "I can only answer questions about this electricity-price forecasting model, its documented evaluation, and operational error metrics.",
            [], "unavailable", route,
        )
    if route in {"dynamic", "mixed"}:
        direct = deterministic_dynamic_answer(question, dynamic_payload)
        if direct is not None and route == "dynamic":
            return direct
    blocks: list[dict] = []
    if route in {"static", "mixed"}:
        _, _, config, _ = _static_index()
        for result in retrieve_static(question):
            if result["score"] >= config["minimum_retrieval_score"]:
                blocks.append({"source_id": result["chunk_id"], "title": result["title"], "text": result["text"]})
    if route in {"dynamic", "mixed"} and dynamic_payload:
        blocks.append(_dynamic_block(dynamic_payload))
    if not blocks:
        return _response("The requested information is unavailable in the supplied project evidence.", [], "insufficient_evidence", route)
    response = _generate(question, blocks, dynamic_payload["status"] if dynamic_payload else "static")
    response["route"] = route
    return response
