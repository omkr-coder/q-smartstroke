"""FastAPI backend for Q-SmartStroke with live background Excel (.xlsx) auto-sync."""

from __future__ import annotations

import asyncio
import io
import hashlib
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from secrets import compare_digest
from base64 import b64encode
from pydantic import BaseModel, Field

from dataset_gen import REQUIRED_COLUMNS
from excel_sync import ExcelAutoSyncService
from quantum_engine import QuantumStrokeEngine


BASE_DIR = Path(__file__).resolve().parent.parent
WORKBOOK_PATH = Path(os.getenv("Q_SMARTSTROKE_WORKBOOK_PATH", str(BASE_DIR / "data" / "q_smartstroke_workbook.xlsx")))
KAGGLE_PATH = BASE_DIR / "data" / "raw" / "healthcare-dataset-stroke-data.csv"
DATA_MODE = os.environ.get("Q_SMARTSTROKE_DATA_MODE", "kaggle")

PUZZLE_CHALLENGES = [
    {
        "id": "puzzle_zz_synergy",
        "level": 1,
        "title": "Hidden Vascular Entanglement",
        "prompt": "Toggle the two medical factors whose combined ZZ interaction produces the highest cohort stroke-rate amplification (>3x baseline).",
        "target_pair": ["hypertension", "heart_disease"],
        "xp": 90,
        "hint": "Look at the two cardiovascular conditions in the constellation.",
    },
    {
        "id": "puzzle_metabolic_age",
        "level": 2,
        "title": "Glycemic Aging Resonance",
        "prompt": "Select the demographic + metabolic pair whose nonlinear synergy sharply elevates risk in older adults.",
        "target_pair": ["age", "avg_glucose_level"],
        "xp": 100,
        "hint": "Combine chronological age (≥60) with hyperglycemia.",
    },
    {
        "id": "puzzle_pressure_load",
        "level": 3,
        "title": "Systolic Age Load",
        "prompt": "Identify the pair connecting aging vasculature with chronic blood pressure.",
        "target_pair": ["age", "hypertension"],
        "xp": 110,
        "hint": "Age combined with blood pressure elevation.",
    },
]


class ProfileInput(BaseModel):
    id: int | None = None
    gender: str = "Female"
    age: float = Field(default=54, ge=0, le=120)
    hypertension: int = Field(default=0, ge=0, le=1)
    heart_disease: int = Field(default=0, ge=0, le=1)
    ever_married: str = "Yes"
    work_type: str = "Private"
    Residence_type: str = "Urban"
    avg_glucose_level: float = Field(default=115.0, ge=30, le=500)
    bmi: float | None = Field(default=27.5, ge=10, le=90)
    smoking_status: str = "never smoked"
    log_to_excel: bool = True


class NewUserInput(BaseModel):
    gender: str = "Female"
    age: float = Field(default=52, ge=0, le=120)
    hypertension: int = Field(default=0, ge=0, le=1)
    heart_disease: int = Field(default=0, ge=0, le=1)
    ever_married: str = "Yes"
    work_type: str = "Private"
    Residence_type: str = "Urban"
    avg_glucose_level: float = Field(default=110.0, ge=30, le=500)
    bmi: float | None = Field(default=26.4, ge=10, le=90)
    smoking_status: str = "never smoked"
    stroke: int = Field(default=0, ge=0, le=1)


class GamificationEventInput(BaseModel):
    module: str
    action_type: str
    item_id: str
    outcome: str
    xp_earned: int = 50
    comprehension_score: float | None = None
    details: str = ""
    badge_to_unlock: str | None = None
    mark_mission_id: str | None = None
    mark_puzzle_id: str | None = None
    safepath_is_correct: bool | None = None


class AutoSaveToggleInput(BaseModel):
    enabled: bool


excel_service: ExcelAutoSyncService | None = None
quantum_engine: QuantumStrokeEngine | None = None
_stop_event = asyncio.Event()
_sync_task: asyncio.Task | None = None


def _retrain_from_external(df: pd.DataFrame) -> None:
    global quantum_engine
    if quantum_engine is not None:
        quantum_engine.fit(df)
        if excel_service is not None:
            excel_service.update_benchmarks(quantum_engine.benchmarks)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global excel_service, quantum_engine, _sync_task
    if DATA_MODE not in {"kaggle", "demo"}:
        raise ValueError("Q_SMARTSTROKE_DATA_MODE must be kaggle or demo")
    excel_service = ExcelAutoSyncService(WORKBOOK_PATH, defer_initial_save=True)
    if DATA_MODE == "kaggle":
        raw = KAGGLE_PATH.read_bytes()
        training_data = pd.read_csv(io.BytesIO(raw))
        missing = set(REQUIRED_COLUMNS) - set(training_data.columns)
        if missing:
            raise ValueError(f"Kaggle CSV is missing columns: {sorted(missing)}")
        quantum_engine = QuantumStrokeEngine(training_data)
        quantum_engine.cohort_stats.update(
            dataset_source="Kaggle / fedesoriano / stroke-prediction-dataset",
            dataset_sha256=hashlib.sha256(raw).hexdigest(),
        )
        excel_service.replace_users_dataset(training_data)
    else:
        quantum_engine = QuantumStrokeEngine(excel_service.get_users_df())
        quantum_engine.cohort_stats["dataset_source"] = "Local workbook (demo mode)"
    excel_service.update_benchmarks(quantum_engine.benchmarks)
    excel_service.force_save_now()

    _stop_event.clear()
    _sync_task = asyncio.create_task(excel_service.auto_sync_loop(_stop_event))
    try:
        yield
    finally:
        _stop_event.set()
        if _sync_task is not None:
            _sync_task.cancel()
            try:
                await _sync_task
            except asyncio.CancelledError:
                pass
        if excel_service is not None:
            excel_service.force_save_now()


app = FastAPI(
    title="Q-SmartStroke API",
    description="Explainable Hybrid Quantum AI & Adaptive Gamification for Stroke Prevention with Live Excel Auto-Sync",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_services() -> tuple[ExcelAutoSyncService, QuantumStrokeEngine]:
    if excel_service is None or quantum_engine is None:
        raise HTTPException(status_code=503, detail="Engine is still initializing")
    return excel_service, quantum_engine


@app.get("/api/health")
def health() -> dict[str, Any]:
    svc, eng = _require_services()
    return {
        "ok": True,
        "sync": svc.get_status(),
        "cohort": eng.cohort_stats,
    }


@app.get("/api/overview")
def get_overview() -> dict[str, Any]:
    svc, eng = _require_services()
    return {
        "cohort": eng.cohort_stats,
        "benchmarks": eng.benchmarks,
        "risk_coverage_curve": eng.risk_coverage_curve,
        "global_interactions": eng.global_interactions,
        "safepath_cases": eng.safepath_cases,
        "puzzles": PUZZLE_CHALLENGES,
        "gamification": svc.get_gamification_state(),
        "excel_sync": svc.get_status(),
    }


def _session(request: Request) -> str:
    try:
        return str(uuid.UUID(request.headers.get("X-Session-ID", "")))
    except ValueError:
        return ""


@app.post("/api/activity")
def record_activity(request: Request, section: str, action: str) -> dict[str, bool]:
    if section not in {"qquest", "explorer", "safepath", "excel"} or action not in {"session_start", "screen_open"}:
        raise HTTPException(status_code=400, detail="Unknown activity")
    svc, _ = _require_services()
    svc.record_activity(section, action, _session(request))
    return {"ok": True}


@app.post("/api/predict")
def predict_stroke_risk(payload: ProfileInput, request: Request) -> dict[str, Any]:
    svc, eng = _require_services()
    profile_dict = payload.model_dump(exclude={"log_to_excel"})
    result = eng.predict_profile(profile_dict)

    svc.record_activity("qquest", "prediction_completed", _session(request), result["confidence_tier"])
    if payload.log_to_excel:
        svc.append_prediction(
            {
                "user_id": payload.id or "custom_user",
                "age": payload.age,
                "gender": payload.gender,
                "hypertension": payload.hypertension,
                "heart_disease": payload.heart_disease,
                "avg_glucose_level": payload.avg_glucose_level,
                "bmi": payload.bmi,
                "smoking_status": payload.smoking_status,
                "qsvm_risk": result["qsvm_risk_pct"],
                "vqc_risk": result["vqc_risk_pct"],
                "hybrid_risk": result["hybrid_risk_pct"],
                "classical_rf_risk": result["classical_rf_pct"],
                "uncertainty_pct": result["uncertainty_pct"],
                "conformal_set": ", ".join(result["conformal_set"]),
                "confidence_tier": result["confidence_tier"],
                "top_interaction": result["top_interaction"],
            }
        )

    return {
        "prediction": result,
        "gamification": svc.get_gamification_state(),
        "excel_sync": svc.get_status(),
    }


@app.post("/api/explore")
def explore_quantum_risk(payload: ProfileInput, request: Request) -> dict[str, Any]:
    svc, eng = _require_services()
    profile_dict = payload.model_dump(exclude={"log_to_excel"})
    result = eng.predict_profile(profile_dict)
    svc.record_activity("explorer", "comparison_completed", _session(request))
    return {
        "prediction": result,
        "excel_sync": svc.get_status(),
    }


@app.post("/api/gamification/event")
def post_gamification_event(payload: GamificationEventInput, request: Request) -> dict[str, Any]:
    svc, _eng = _require_services()
    res = svc.record_gamification_event(
        module=payload.module,
        action_type=payload.action_type,
        item_id=payload.item_id,
        outcome=payload.outcome,
        xp_earned=payload.xp_earned,
        comprehension_score=payload.comprehension_score,
        details=payload.details,
        badge_to_unlock=payload.badge_to_unlock,
        mark_mission_id=payload.mark_mission_id,
        mark_puzzle_id=payload.mark_puzzle_id,
        safepath_is_correct=payload.safepath_is_correct,
        session_id=_session(request),
    )
    return {
        "gamification": res["gamification"],
        "event": res["event"],
        "excel_sync": svc.get_status(),
    }


@app.get("/api/excel/status")
def excel_status() -> dict[str, Any]:
    svc, _ = _require_services()
    return svc.get_status()


@app.post("/api/excel/sync-now")
def excel_sync_now() -> dict[str, Any]:
    svc, _ = _require_services()
    return svc.force_save_now()


@app.post("/api/excel/auto-save")
def toggle_auto_save(payload: AutoSaveToggleInput) -> dict[str, Any]:
    svc, _ = _require_services()
    return svc.set_auto_save(payload.enabled)


@app.get("/api/excel/sheet/{sheet_name}")
def get_excel_sheet(
    sheet_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=5, le=100),
    search: str = Query(default=""),
) -> dict[str, Any]:
    svc, _ = _require_services()
    try:
        return svc.get_sheet_preview(sheet_name=sheet_name, page=page, page_size=page_size, search=search)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/excel/users")
def add_user_to_excel(payload: NewUserInput) -> dict[str, Any]:
    svc, eng = _require_services()
    row = svc.add_user_row(payload.model_dump())
    pred = eng.predict_profile(row)
    svc.append_prediction(
        {
            "user_id": row["id"],
            "age": row["age"],
            "gender": row["gender"],
            "hypertension": row["hypertension"],
            "heart_disease": row["heart_disease"],
            "avg_glucose_level": row["avg_glucose_level"],
            "bmi": None if pd.isna(row["bmi"]) else row["bmi"],
            "smoking_status": row["smoking_status"],
            "qsvm_risk": pred["qsvm_risk_pct"],
            "vqc_risk": pred["vqc_risk_pct"],
            "hybrid_risk": pred["hybrid_risk_pct"],
            "classical_rf_risk": pred["classical_rf_pct"],
            "uncertainty_pct": pred["uncertainty_pct"],
            "conformal_set": ", ".join(pred["conformal_set"]),
            "confidence_tier": pred["confidence_tier"],
            "top_interaction": pred["top_interaction"],
        }
    )
    return {
        "added_user": {k: (None if pd.isna(v) else v) for k, v in row.items()},
        "prediction": pred,
        "excel_sync": svc.get_status(),
    }


@app.post("/api/excel/upload")
async def upload_dataset(file: UploadFile = File(...)) -> dict[str, Any]:
    global quantum_engine
    svc, eng = _require_services()
    filename = (file.filename or "").lower()
    raw = await file.read()

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw))
        elif filename.endswith((".xlsx", ".xls")):
            xl = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
            target_sheet = "Users_Dataset" if "Users_Dataset" in xl.sheet_names else xl.sheet_names[0]
            df = xl.parse(target_sheet)
        else:
            raise HTTPException(status_code=400, detail="Please upload a .csv or .xlsx file.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse uploaded file: {exc}") from exc

    # Normalize column names if case differs slightly (e.g., residence_type -> Residence_type)
    col_lookup = {c.lower(): c for c in df.columns}
    rename_map = {}
    for req in REQUIRED_COLUMNS:
        if req not in df.columns and req.lower() in col_lookup:
            rename_map[col_lookup[req.lower()]] = req
    if rename_map:
        df = df.rename(columns=rename_map)

    try:
        missing = set(REQUIRED_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"Uploaded dataset is missing columns: {sorted(missing)}")
        eng = QuantumStrokeEngine(df)
        eng.cohort_stats.update(
            dataset_source="Uploaded dataset", dataset_sha256=hashlib.sha256(raw).hexdigest()
        )
        count = svc.replace_users_dataset(df)
        quantum_engine = eng
        svc.record_activity("excel", "dataset_training_completed", outcome="success")
        svc.update_benchmarks(eng.benchmarks)
        svc.force_save_now()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "rows_loaded": count,
        "cohort": eng.cohort_stats,
        "benchmarks": eng.benchmarks,
        "excel_sync": svc.get_status(),
    }


@app.get("/api/excel/download")
def download_excel_workbook() -> FileResponse:
    svc, _ = _require_services()
    svc.force_save_now()
    if not svc.workbook_path.exists():
        raise HTTPException(status_code=404, detail="Excel workbook not found")
    return FileResponse(
        path=svc.workbook_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="q_smartstroke_workbook.xlsx",
    )

# The production image serves the React build and API from one origin.
dist = BASE_DIR / "frontend" / "dist"
publish_user = os.getenv("Q_SMARTSTROKE_WEB_USER")
publish_password = os.getenv("Q_SMARTSTROKE_WEB_PASSWORD")
if bool(publish_user) != bool(publish_password):
    raise RuntimeError("Set both Q_SMARTSTROKE_WEB_USER and Q_SMARTSTROKE_WEB_PASSWORD")

if publish_user and publish_password:
    expected_auth = b"Basic " + b64encode(f"{publish_user}:{publish_password}".encode("utf-8"))

    @app.middleware("http")
    async def require_web_access(request: Request, call_next):
        provided = request.headers.get("authorization", "").encode("utf-8")
        if not compare_digest(provided, expected_auth):
            return PlainTextResponse(
                "Authentication required", status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Q-SmartStroke", charset="UTF-8"'},
            )
        return await call_next(request)

if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
