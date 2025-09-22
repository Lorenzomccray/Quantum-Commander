from __future__ import annotations
from typing import List, Dict, Any, Tuple
from functools import lru_cache
from pathlib import Path
from datetime import datetime
import os
import json
import re
import time
import logging

# Use the existing agent implementation and expose a sync call
from commander.agent import run_once

# Set up a dedicated logger that always writes to data/logs
_repo_root = Path(__file__).resolve().parent.parent
_log_dir = _repo_root / "data" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / f"ensemble_{datetime.now().strftime('%Y%m%d')}.log"

_logger = logging.getLogger("ensemble")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    try:
        _fh = logging.FileHandler(str(_log_file))
        _fh.setLevel(logging.INFO)
        _fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        _logger.addHandler(_fh)
    except Exception:
        # Best-effort: if file handler fails, fall back to stderr
        _sh = logging.StreamHandler()
        _sh.setLevel(logging.INFO)
        _sh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        _logger.addHandler(_sh)


def _validate_model_config(model_config: Dict[str, str]) -> bool:
    required = ["provider", "model"]
    return all(field in model_config for field in required)


def _parse_models(env_val: str | None) -> List[Dict[str, str]]:
    if not env_val:
        return []
    env_val = env_val.strip()
    try:
        data = json.loads(env_val)
        if isinstance(data, list):
            return [m for m in data if _validate_model_config(m)]
    except Exception as e:
        _logger.warning(f"Failed to parse ENSEMBLE_MODELS JSON: {e}")

    res: List[Dict[str, str]] = []
    for part in env_val.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            p, m = part.split(":", 1)
            model_config = {"provider": p.strip(), "model": m.strip()}
            if _validate_model_config(model_config):
                res.append(model_config)
            else:
                _logger.warning(f"Invalid model config skipped: {model_config}")
    return res


def _get_fallback_response(message: str) -> str:
    return (
        "I apologize, but I'm unable to provide a response at this time. "
        f"Please try again later or simplify your query: {message[:100]}..."
    )


def _calculate_confidence(question: str, response: str) -> float:
    question_len = len((question or "").split())
    response_len = len((response or "").split())
    if question_len == 0 or response_len == 0:
        return 0.0
    ratio = response_len / question_len
    ratio_factor = min(1.0, ratio / 5.0)
    error_indicators = ["sorry", "error", "unable", "cannot", "as an ai"]
    lower_response = response.lower()
    error_score = sum(1 for indicator in error_indicators if indicator in lower_response)
    confidence = max(0.1, 0.7 - (error_score * 0.1) + (ratio_factor * 0.3))
    return min(1.0, confidence)


@lru_cache(maxsize=100)
def _cached_model_call(provider: str, model: str, message: str, temperature: float, max_tokens: int) -> str:
    return run_once(
        provider=provider,
        model=model,
        message=message,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _judge(
    question: str,
    candidates: List[Tuple[str, str]],
    judge_provider: str,
    judge_model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    numbered = "\n\n".join(f"[{i}] ({label})\n{text}" for i, (label, text) in enumerate(candidates))
    prompt = f"""You are a careful evaluator. Pick the best answer by index.
Question:
{question}

Candidates:
{numbered}

Rules:
- Consider correctness, completeness, clarity, and citations if present.
- Prefer answers that are non-empty and contain useful substance; avoid picking empty or trivial outputs.
- Reply ONLY with the index number (e.g., 0 or 1 or 2). No explanation."""

    try:
        out = _cached_model_call(
            provider=judge_provider,
            model=judge_model,
            message=prompt,
            temperature=min(0.2, temperature),
            max_tokens=16,
        ).strip()
        m = re.search(r"\b(\d+)\b", out)
        idx = int(m.group(1)) if m else 0
        idx = max(0, min(idx, len(candidates) - 1))
        chosen_response = candidates[idx][1]
        confidence = _calculate_confidence(question, chosen_response)
        _logger.info(f"Judge selected candidate {idx} with confidence {confidence:.2f}")
        return chosen_response
    except Exception as e:
        _logger.error(f"Judge model failed: {e}")
        return candidates[0][1] if candidates else _get_fallback_response(question)


def _router_choice(question: str, pool: List[Dict[str, str]]) -> Dict[str, str]:
    q = (question or "").lower()
    if any(k in q for k in ("law", "statute", "fdcpa", "ucc", "tax", "irs", "contract")):
        for m in pool:
            if m["provider"] in ("anthropic", "openai"):
                return m
    if len(question) > 1200:
        for p in ("openai", "anthropic", "deepseek", "groq"):
            for m in pool:
                if m["provider"] == p:
                    return m
    return pool[0] if pool else {"provider": "openai", "model": "gpt-4o"}


def _get_default_models() -> List[Dict[str, str]]:
    pool: List[Dict[str, str]] = [
        {"provider": "openai", "model": os.getenv("OPENAI_MODEL", "gpt-4o")},
        {"provider": "anthropic", "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")},
    ]
    if os.getenv("GROQ_API_KEY"):
        pool.append({"provider": "groq", "model": os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")})
    if os.getenv("DEEPSEEK_API_KEY"):
        pool.append({"provider": "deepseek", "model": os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")})
    return pool


def run_ensemble(
    message: str,
    temperature: float = 0.2,
    max_tokens: int = 800,
    mode: str | None = None,
    models: List[Dict[str, str]] | None = None,
    judge_provider: str | None = None,
    judge_model: str | None = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    if not message or not message.strip():
        return {"response": "Empty query received", "meta": {"error": "Empty query"}}

    mode = (mode or os.getenv("ENSEMBLE_MODE", "committee")).lower()
    pool = models or _parse_models(os.getenv("ENSEMBLE_MODELS"))

    validated_models: List[Dict[str, str]] = []
    for model in pool:
        if _validate_model_config(model):
            validated_models.append(model)
        else:
            _logger.warning(f"Invalid model config skipped: {model}")

    pool = validated_models if validated_models else _get_default_models()
    if not pool:
        _logger.error("No valid models available for ensemble")
        return {"response": _get_fallback_response(message), "meta": {"error": "No models available"}}

    start = time.time()
    meta: Dict[str, Any] = {"mode": mode, "candidates": [], "chosen": None, "elapsed_s": None, "confidence": None}

    try:
        if mode == "router":
            choice = _router_choice(message, pool)
            text = _cached_model_call(
                provider=choice["provider"],
                model=choice["model"],
                message=message,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            meta["chosen"] = choice
            meta["winner"] = {"provider": choice["provider"], "model": choice["model"]}
            meta["confidence"] = _calculate_confidence(message, text)
            meta["elapsed_s"] = round(time.time() - start, 3)
            return {"response": text, "meta": meta}

        if mode == "cascade":
            best_text = ""
            best_score = 0
            best_model: Dict[str, str] | None = None
            for m in pool:
                try:
                    t = _cached_model_call(
                        provider=m["provider"],
                        model=m["model"],
                        message=message,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    score = len(t.strip())
                    confidence = _calculate_confidence(message, t)
                    meta["candidates"].append({"model": m, "len": score, "confidence": confidence})
                    if score > best_score:
                        best_text, best_score, best_model = t, score, m
                    if score >= max_tokens:
                        break
                except Exception as e:
                    _logger.error(f"Model {m['provider']}:{m['model']} failed: {e}")
                    meta["candidates"].append({"model": m, "error": str(e)})
                    continue
            meta["chosen"] = best_model
            if best_model:
                meta["winner"] = {"provider": best_model.get("provider"), "model": best_model.get("model")}
            if best_text:
                meta["confidence"] = _calculate_confidence(message, best_text)
            meta["elapsed_s"] = round(time.time() - start, 3)
            return {"response": best_text or _get_fallback_response(message), "meta": meta}

        # committee + judge (default)
        judge_provider = judge_provider or os.getenv("ENSEMBLE_JUDGE_PROVIDER", os.getenv("MODEL_PROVIDER", "openai"))
        judge_model = judge_model or os.getenv("ENSEMBLE_JUDGE_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o"))
        candidates: List[Tuple[str, str]] = []

        for m in pool:
            label = f"{m['provider']}:{m['model']}"
            try:
                t = _cached_model_call(
                    provider=m["provider"],
                    model=m["model"],
                    message=message,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                confidence = _calculate_confidence(message, t)
                candidates.append((label, t))
                meta["candidates"].append({"model": m, "len": len(t.strip()), "confidence": confidence})
            except Exception as e:
                _logger.error(f"Model {m['provider']}:{m['model']} failed: {e}")
                meta["candidates"].append({"model": m, "error": str(e)})

        if not candidates:
            _logger.error("All models failed for this request")
            return {"response": _get_fallback_response(message), "meta": meta}

        chosen = _judge(message, candidates, judge_provider, judge_model, temperature, max_tokens)
        # Attempt to identify the winning candidate by exact match
        winner_label = None
        for label, text in candidates:
            if text == chosen:
                winner_label = label
                break
        # Guardrail: if judge produces an empty choice, fall back to best non-empty by confidence/length
        if (not chosen or not chosen.strip()) and candidates:
            try:
                best_label, best_text = max(
                    candidates,
                    key=lambda pair: (_calculate_confidence(message, pair[1]), len(pair[1].strip())),
                )
                meta["chosen_fallback"] = "non_empty_best"
                chosen = best_text
                winner_label = best_label
            except Exception:
                pass
        # Fill winner fields if we have a label like provider:model
        if winner_label and ":" in winner_label:
            prov, mod = winner_label.split(":", 1)
            meta["winner"] = {"provider": prov, "model": mod}
        meta["chosen"] = {"provider": judge_provider, "model": judge_model, "role": "judge"}
        meta["confidence"] = _calculate_confidence(message, chosen)
        meta["elapsed_s"] = round(time.time() - start, 3)
        return {"response": chosen, "meta": meta}

    except Exception as e:
        _logger.error(f"Ensemble processing failed: {e}")
        return {"response": _get_fallback_response(message), "meta": {"error": str(e), "mode": mode}}

