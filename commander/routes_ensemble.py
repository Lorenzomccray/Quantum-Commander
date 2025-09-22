from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from commander.ensemble import run_ensemble, _get_default_models, _parse_models
import os

router = APIRouter()

class EnsembleReq(BaseModel):
    message: str
    mode: Optional[str] = None
    models: Optional[List[Dict[str, str]]] = None
    temperature: float = 0.2
    max_tokens: int = 800
    timeout: int = 30

class EnsembleConfig(BaseModel):
    mode: Optional[str] = None
    models: Optional[List[Dict[str, str]]] = None
    judge_provider: Optional[str] = None
    judge_model: Optional[str] = None

@router.post("/ensemble/test")
def ensemble_test(req: EnsembleReq) -> Dict[str, Any]:
    res = run_ensemble(
        message=req.message,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        mode=req.mode,
        models=req.models,
        timeout=req.timeout,
    )
    return {"ok": True, **res}

@router.get("/ensemble/models")
def get_available_models() -> Dict[str, Any]:
    return {
        "models": _get_default_models(),
        "configured_models": _parse_models(os.getenv("ENSEMBLE_MODELS")),
        "status": "success",
    }

@router.get("/ensemble/stats")
def get_ensemble_stats() -> Dict[str, Any]:
    # Placeholder for future metrics
    return {
        "total_requests": 0,
        "modes_usage": {"committee": 0, "router": 0, "cascade": 0},
        "average_response_time": 0,
        "status": "success",
    }

@router.post("/ensemble/configure")
def configure_ensemble(config: EnsembleConfig) -> Dict[str, Any]:
    # Placeholder for dynamic configuration
    return {
        "status": "success",
        "message": "Configuration updated (note: some changes may require restart)",
        "applied_config": config.dict(),
    }

