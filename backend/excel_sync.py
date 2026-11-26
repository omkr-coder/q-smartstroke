"""Thread-safe background Excel (.xlsx) persistence and auto-sync engine."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from dataset_gen import REQUIRED_COLUMNS, generate_stroke_dataset


PREDICTION_COLUMNS = [
    "log_id",
    "timestamp",
    "user_id",
    "age",
    "gender",
    "hypertension",
    "heart_disease",
    "avg_glucose_level",
    "bmi",
    "smoking_status",
    "qsvm_risk",
    "vqc_risk",
    "hybrid_risk",
    "classical_rf_risk",
    "uncertainty_pct",
    "conformal_set",
    "confidence_tier",
    "top_interaction",
]

GAMIFICATION_COLUMNS = [
    "player_id",
    "xp",
    "level",
    "streak_days",
    "missions_completed",
    "puzzles_solved",
    "safepath_cases",
    "safepath_correct",
    "badges_json",
    "completed_mission_ids_json",
    "solved_puzzle_ids_json",
    "updated_at",
]

TELEMETRY_COLUMNS = [
    "event_id",
    "timestamp",
    "module",
    "action_type",
    "session_id",
    "item_id",
    "outcome",
    "xp_earned",
    "comprehension_score",
    "details",
]

BENCHMARK_COLUMNS = [
    "model_name",
    "family",
    "roc_auc",
    "pr_auc",
    "f1_score",
    "recall",
    "precision",
    "brier_score",
    "ece",
    "evaluated_at",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class ExcelAutoSyncService:
    """Manages an in-memory multi-sheet state backed by an auto-saving Excel workbook."""

    def __init__(
        self,
        workbook_path: Path,
        on_external_dataset_reload: Callable[[pd.DataFrame], None] | None = None,
        defer_initial_save: bool = False,
    ):
        self.workbook_path = Path(workbook_path)
        self.workbook_path.parent.mkdir(parents=True, exist_ok=True)
        self.on_external_dataset_reload = on_external_dataset_reload
        self._defer_initial_save = defer_initial_save

        self._lock = threading.RLock()
        self._dirty = False
        self._last_mutation_ts = 0.0
        self._last_saved_ts: float | None = None
        self._last_saved_iso: str | None = None
        self._last_error: str | None = None
        self._status = "initializing"
        self._auto_save_enabled = True
        self._debounce_seconds = 1.2
        self._save_count = 0
        self._pending_changes = 0
        self._last_known_mtime: float | None = None
        self._last_known_size: int | None = None
        self._is_saving = False

        self.users_df: pd.DataFrame = pd.DataFrame(columns=REQUIRED_COLUMNS)
        self.predictions_df: pd.DataFrame = pd.DataFrame(columns=PREDICTION_COLUMNS)
        self.gamification_df: pd.DataFrame = pd.DataFrame(columns=GAMIFICATION_COLUMNS)
        self.telemetry_df: pd.DataFrame = pd.DataFrame(columns=TELEMETRY_COLUMNS)
        self.benchmarks_df: pd.DataFrame = pd.DataFrame(columns=BENCHMARK_COLUMNS)

        self._initialize_or_load()

    def _default_gamification_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "player_id": "researcher_1",
                    "xp": 0,
                    "level": 1,
                    "streak_days": 1,
                    "missions_completed": 0,
                    "puzzles_solved": 0,
                    "safepath_cases": 0,
                    "safepath_correct": 0,
                    "badges_json": "[]",
                    "completed_mission_ids_json": "[]",
                    "solved_puzzle_ids_json": "[]",
                    "updated_at": _utc_now_iso(),
                }
            ]
        )

    def _initialize_or_load(self) -> None:
        with self._lock:
            if self.workbook_path.exists():
                try:
                    self._load_from_disk_locked()
                    self._status = "synced"
                    return
                except Exception as exc:
                    self._last_error = f"Loaded fallback after read error: {exc}"

            self.users_df = generate_stroke_dataset(n_users=5000, seed=42)
            self.predictions_df = pd.DataFrame(columns=PREDICTION_COLUMNS)
            self.gamification_df = self._default_gamification_df()
            self.telemetry_df = pd.DataFrame(columns=TELEMETRY_COLUMNS)
            self.benchmarks_df = pd.DataFrame(columns=BENCHMARK_COLUMNS)
            if not self._defer_initial_save:
                self._save_to_disk_locked()
            self._status = "synced"

    def _load_from_disk_locked(self) -> None:
        xl = pd.ExcelFile(self.workbook_path, engine="openpyxl")
        sheets = set(xl.sheet_names)

        if "Users_Dataset" in sheets:
            df = xl.parse("Users_Dataset")
            for col in REQUIRED_COLUMNS:
                if col not in df.columns:
                    raise ValueError(f"Missing column '{col}' in Users_Dataset")
            self.users_df = df[REQUIRED_COLUMNS].copy()
        else:
            # Support workbooks whose first sheet is the raw 12-column dataset
            first_df = xl.parse(xl.sheet_names[0])
            if all(c in first_df.columns for c in REQUIRED_COLUMNS):
                self.users_df = first_df[REQUIRED_COLUMNS].copy()
            else:
                self.users_df = generate_stroke_dataset(n_users=5000, seed=42)

        self.predictions_df = (
            xl.parse("Predictions_Log") if "Predictions_Log" in sheets else pd.DataFrame(columns=PREDICTION_COLUMNS)
        )
        if "Gamification_Progress" in sheets:
            gdf = xl.parse("Gamification_Progress")
            self.gamification_df = gdf if not gdf.empty else self._default_gamification_df()
        else:
            self.gamification_df = self._default_gamification_df()

        self.telemetry_df = (
            xl.parse("Interaction_Telemetry") if "Interaction_Telemetry" in sheets else pd.DataFrame(columns=TELEMETRY_COLUMNS)
        )
        self.benchmarks_df = (
            xl.parse("Model_Benchmarks") if "Model_Benchmarks" in sheets else pd.DataFrame(columns=BENCHMARK_COLUMNS)
        )

        st = self.workbook_path.stat()
        self._last_known_mtime = st.st_mtime
        self._last_known_size = st.st_size
        self._last_saved_iso = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def _write_df_to_sheet(self, wb: Workbook, title: str, df: pd.DataFrame, tab_color: str) -> None:
        ws = wb.create_sheet(title=title)
        ws.sheet_properties.tabColor = tab_color

        headers = list(df.columns)
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="F8FAFC")

        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Clean values without NaN so openpyxl writes clean blank Excel cells
        clean_df = df.astype(object).where(pd.notnull(df), None)
        for row in clean_df.itertuples(index=False, name=None):
            ws.append(row)

        ws.freeze_panes = "A2"
        if len(headers) > 0:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(len(df) + 1, 1)}"

        # Set readable column widths based on header + sample rows
        sample_rows = clean_df.head(40)
        for idx, col_name in enumerate(headers, start=1):
            max_len = len(str(col_name))
            for val in sample_rows[col_name]:
                if val is not None:
                    max_len = max(max_len, min(len(str(val)), 42))
            ws.column_dimensions[get_column_letter(idx)].width = max(max_len + 4, 12)

    def _save_to_disk_locked(self) -> bool:
        self._is_saving = True
        tmp_path = self.workbook_path.with_suffix(".tmp.xlsx")
        try:
            wb = Workbook()
            # Remove default empty sheet after creating our sheets
            default_ws = wb.active

            self._write_df_to_sheet(wb, "Users_Dataset", self.users_df, "0EA5E9")
            self._write_df_to_sheet(wb, "Predictions_Log", self.predictions_df, "8B5CF6")
            self._write_df_to_sheet(wb, "Gamification_Progress", self.gamification_df, "10B981")
            self._write_df_to_sheet(wb, "Interaction_Telemetry", self.telemetry_df, "F59E0B")
            self._write_df_to_sheet(wb, "Model_Benchmarks", self.benchmarks_df, "EC4899")

            wb.remove(default_ws)
            wb.save(tmp_path)
            os.replace(tmp_path, self.workbook_path)

            st = self.workbook_path.stat()
            self._last_known_mtime = st.st_mtime
            self._last_known_size = st.st_size
            self._last_saved_ts = time.time()
            self._last_saved_iso = _utc_now_iso()
            self._dirty = False
            self._pending_changes = 0
            self._save_count += 1
            self._last_error = None
            self._status = "synced"
            return True
        except PermissionError:
            self._status = "locked_retrying"
            self._last_error = "Workbook is currently open in Excel; changes queued and will auto-save once released."
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            return False
        except Exception as exc:
            self._status = "error"
            self._last_error = str(exc)
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            return False
        finally:
            self._is_saving = False

    def _mark_dirty_locked(self) -> None:
        self._dirty = True
        self._pending_changes += 1
        self._last_mutation_ts = time.time()
        self._status = "pending_save"

    def force_save_now(self) -> dict[str, Any]:
        with self._lock:
            self._save_to_disk_locked()
            return self.get_status()

    def set_auto_save(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            self._auto_save_enabled = enabled
            return self.get_status()

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "auto_save_enabled": self._auto_save_enabled,
                "dirty": self._dirty,
                "pending_changes": self._pending_changes,
                "last_saved_at": self._last_saved_iso,
                "save_count": self._save_count,
                "workbook_path": str(self.workbook_path.resolve()),
                "workbook_filename": self.workbook_path.name,
                "last_error": self._last_error,
                "sheet_counts": {
                    "Users_Dataset": int(len(self.users_df)),
                    "Predictions_Log": int(len(self.predictions_df)),
                    "Gamification_Progress": int(len(self.gamification_df)),
                    "Interaction_Telemetry": int(len(self.telemetry_df)),
                    "Model_Benchmarks": int(len(self.benchmarks_df)),
                },
            }

    def get_users_df(self) -> pd.DataFrame:
        with self._lock:
            return self.users_df.copy()

    def add_user_row(self, user_data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            next_id = int(pd.to_numeric(self.users_df["id"], errors="coerce").max() or 5000) + 1
            row = {
                "id": int(user_data.get("id") or next_id),
                "gender": user_data.get("gender", "Female"),
                "age": float(user_data.get("age", 45)),
                "hypertension": int(user_data.get("hypertension", 0)),
                "heart_disease": int(user_data.get("heart_disease", 0)),
                "ever_married": user_data.get("ever_married", "Yes"),
                "work_type": user_data.get("work_type", "Private"),
                "Residence_type": user_data.get("Residence_type", "Urban"),
                "avg_glucose_level": float(user_data.get("avg_glucose_level", 105.0)),
                "bmi": float(user_data["bmi"]) if user_data.get("bmi") not in (None, "", "N/A") else np.nan,
                "smoking_status": user_data.get("smoking_status", "never smoked"),
                "stroke": int(user_data.get("stroke", 0)),
            }
            self.users_df = pd.concat([self.users_df, pd.DataFrame([row])], ignore_index=True)
            self._mark_dirty_locked()
            return row

    def replace_users_dataset(self, new_df: pd.DataFrame) -> int:
        missing = [c for c in REQUIRED_COLUMNS if c not in new_df.columns]
        if missing:
            raise ValueError(f"Uploaded file is missing required columns: {', '.join(missing)}")
        with self._lock:
            self.users_df = new_df[REQUIRED_COLUMNS].copy()
            self._mark_dirty_locked()
            self._save_to_disk_locked()
            return int(len(self.users_df))

    def append_prediction(self, entry: dict[str, Any]) -> None:
        with self._lock:
            row = {col: entry.get(col) for col in PREDICTION_COLUMNS}
            row["log_id"] = row["log_id"] or f"PRED-{uuid.uuid4().hex[:8].upper()}"
            row["timestamp"] = row["timestamp"] or _utc_now_iso()
            self.predictions_df = pd.concat([pd.DataFrame([row]), self.predictions_df], ignore_index=True)
            self._mark_dirty_locked()

    def get_gamification_state(self) -> dict[str, Any]:
        with self._lock:
            row = self.gamification_df.iloc[0].to_dict()
            return {
                "player_id": str(row.get("player_id", "researcher_1")),
                "xp": int(row.get("xp", 0)),
                "level": int(row.get("level", 1)),
                "streak_days": int(row.get("streak_days", 1)),
                "missions_completed": int(row.get("missions_completed", 0)),
                "puzzles_solved": int(row.get("puzzles_solved", 0)),
                "safepath_cases": int(row.get("safepath_cases", 0)),
                "safepath_correct": int(row.get("safepath_correct", 0)),
                "badges": json.loads(str(row.get("badges_json") or "[]")),
                "completed_mission_ids": json.loads(str(row.get("completed_mission_ids_json") or "[]")),
                "solved_puzzle_ids": json.loads(str(row.get("solved_puzzle_ids_json") or "[]")),
                "updated_at": str(row.get("updated_at") or _utc_now_iso()),
            }

    def record_gamification_event(
        self,
        module: str,
        action_type: str,
        item_id: str,
        outcome: str,
        xp_earned: int,
        comprehension_score: float | None = None,
        details: str = "",
        badge_to_unlock: str | None = None,
        mark_mission_id: str | None = None,
        mark_puzzle_id: str | None = None,
        safepath_is_correct: bool | None = None,
        session_id: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            state = self.get_gamification_state()

            already_done = (
                (mark_mission_id and mark_mission_id in state["completed_mission_ids"])
                or (mark_puzzle_id and mark_puzzle_id in state["solved_puzzle_ids"])
            )
            awarded_xp = 0 if already_done else max(0, int(xp_earned))
            state["xp"] += awarded_xp
            state["level"] = 1 + (state["xp"] // 150)

            if mark_mission_id and mark_mission_id not in state["completed_mission_ids"]:
                state["completed_mission_ids"].append(mark_mission_id)
                state["missions_completed"] = len(state["completed_mission_ids"])

            if mark_puzzle_id and mark_puzzle_id not in state["solved_puzzle_ids"]:
                state["solved_puzzle_ids"].append(mark_puzzle_id)
                state["puzzles_solved"] = len(state["solved_puzzle_ids"])

            if safepath_is_correct is not None:
                state["safepath_cases"] += 1
                if safepath_is_correct:
                    state["safepath_correct"] += 1

            # Auto-award milestone badges
            badges = set(state["badges"])
            if badge_to_unlock:
                badges.add(badge_to_unlock)
            if state["missions_completed"] >= 1:
                badges.add("Q-Quest Initiator")
            if state["missions_completed"] >= 4:
                badges.add("Prevention Champion")
            if state["puzzles_solved"] >= 2:
                badges.add("Quantum Entangler")
            if state["safepath_correct"] >= 3:
                badges.add("Conformal Guardian")
            if state["xp"] >= 500:
                badges.add("Q-SmartStroke Master")
            state["badges"] = sorted(badges)

            self.gamification_df = pd.DataFrame(
                [
                    {
                        "player_id": state["player_id"],
                        "xp": state["xp"],
                        "level": state["level"],
                        "streak_days": state["streak_days"],
                        "missions_completed": state["missions_completed"],
                        "puzzles_solved": state["puzzles_solved"],
                        "safepath_cases": state["safepath_cases"],
                        "safepath_correct": state["safepath_correct"],
                        "badges_json": json.dumps(state["badges"]),
                        "completed_mission_ids_json": json.dumps(state["completed_mission_ids"]),
                        "solved_puzzle_ids_json": json.dumps(state["solved_puzzle_ids"]),
                        "updated_at": _utc_now_iso(),
                    }
                ]
            )

            tel_row = {
                "event_id": f"EVT-{uuid.uuid4().hex[:8].upper()}",
                "timestamp": _utc_now_iso(),
                "module": module,
                "action_type": action_type,
                "item_id": item_id,
                "outcome": outcome,
                "xp_earned": awarded_xp,
                "comprehension_score": comprehension_score,
                "session_id": session_id,
                "details": "",
            }
            self.telemetry_df = pd.concat([self.telemetry_df, pd.DataFrame([tel_row])], ignore_index=True).reindex(columns=TELEMETRY_COLUMNS)
            self._mark_dirty_locked()
            return {"gamification": self.get_gamification_state(), "event": tel_row}

    def record_activity(self, module: str, action: str, session: str = "", outcome: str = "") -> None:
        with self._lock:
            row = {
                "event_id": uuid.uuid4().hex,
                "timestamp": _utc_now_iso(),
                "session_id": session,
                "module": module,
                "action_type": action,
                "outcome": outcome,
            }
            self.telemetry_df = pd.concat(
                [self.telemetry_df, pd.DataFrame([row])], ignore_index=True
            ).reindex(columns=TELEMETRY_COLUMNS)
            self._mark_dirty_locked()

    def update_benchmarks(self, benchmarks: list[dict[str, Any]]) -> None:
        with self._lock:
            now = _utc_now_iso()
            rows = [{**b, "evaluated_at": now} for b in benchmarks]
            self.benchmarks_df = pd.DataFrame(rows, columns=BENCHMARK_COLUMNS)
            self._mark_dirty_locked()

    def get_sheet_preview(self, sheet_name: str, page: int = 1, page_size: int = 25, search: str = "") -> dict[str, Any]:
        with self._lock:
            mapping = {
                "Users_Dataset": self.users_df,
                "Predictions_Log": self.predictions_df,
                "Gamification_Progress": self.gamification_df,
                "Interaction_Telemetry": self.telemetry_df,
                "Model_Benchmarks": self.benchmarks_df,
            }
            if sheet_name not in mapping:
                raise ValueError(f"Unknown sheet: {sheet_name}")

            df = mapping[sheet_name].copy()
            if search.strip():
                q = search.strip().lower()
                mask = df.astype(str).apply(lambda col: col.str.lower().str.contains(q, regex=False)).any(axis=1)
                df = df[mask]

            total = len(df)
            start = max(0, (page - 1) * page_size)
            end = start + page_size
            slice_df = df.iloc[start:end].astype(object).where(pd.notnull(df.iloc[start:end]), None)
            return {
                "sheet_name": sheet_name,
                "columns": list(df.columns),
                "rows": slice_df.to_dict(orient="records"),
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    async def auto_sync_loop(self, stop_event: asyncio.Event) -> None:
        """Continuously flushes dirty state to Excel and detects external Excel edits."""
        while not stop_event.is_set():
            try:
                await asyncio.sleep(1.0)
                should_save = False
                external_reloaded_df: pd.DataFrame | None = None

                with self._lock:
                    now = time.time()
                    # Check if external process modified the Excel file when we are not dirty
                    if not self._dirty and not self._is_saving and self.workbook_path.exists():
                        try:
                            st = self.workbook_path.stat()
                            if (
                                self._last_known_mtime is not None
                                and (abs(st.st_mtime - self._last_known_mtime) > 0.5 or st.st_size != self._last_known_size)
                            ):
                                old_len = len(self.users_df)
                                self._load_from_disk_locked()
                                if len(self.users_df) != old_len or True:
                                    external_reloaded_df = self.users_df.copy()
                                self._status = "synced_external"
                        except Exception:
                            pass

                    if self._dirty and self._auto_save_enabled:
                        elapsed = now - self._last_mutation_ts
                        if elapsed >= self._debounce_seconds:
                            should_save = True

                if external_reloaded_df is not None and self.on_external_dataset_reload is not None:
                    await asyncio.to_thread(self.on_external_dataset_reload, external_reloaded_df)

                if should_save:
                    await asyncio.to_thread(self.force_save_now)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(2.0)
