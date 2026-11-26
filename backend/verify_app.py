"""End-to-end verification for Q-SmartStroke live uvicorn server, QML models, and background Excel auto-save."""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from openpyxl import load_workbook

BACKEND_DIR = Path(__file__).resolve().parent
WORKBOOK_PATH = BACKEND_DIR.parent / "data" / "q_smartstroke_workbook.xlsx"
BASE_URL = "http://127.0.0.1:8765"


def http_json(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_verification() -> None:
    if WORKBOOK_PATH.exists():
        WORKBOOK_PATH.unlink()

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8765"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        # Wait for server startup + 5,000-user QML training
        deadline = time.time() + 60
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(f"Server exited early with code {proc.returncode}:\n{out}")
            try:
                h = http_json("GET", "/api/health")
                if h.get("ok"):
                    break
            except Exception:
                time.sleep(0.6)
        else:
            proc.terminate()
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"Server failed to start within 60s:\n{out}")

        ov = http_json("GET", "/api/overview")
        assert ov["cohort"]["total_users"] == 5000
        assert len(ov["benchmarks"]) == 7
        print("Cohort:", ov["cohort"])
        print("Top Benchmark:", ov["benchmarks"][0])

        pred_res = http_json(
            "POST",
            "/api/predict",
            {
                "gender": "Male",
                "age": 67,
                "hypertension": 1,
                "heart_disease": 1,
                "ever_married": "Yes",
                "work_type": "Self-employed",
                "Residence_type": "Urban",
                "avg_glucose_level": 210.0,
                "bmi": 31.2,
                "smoking_status": "formerly smoked",
                "log_to_excel": True,
            },
        )
        pred = pred_res["prediction"]
        assert len(pred["qubit_states"]) == 6
        assert len(pred["missions"]) >= 3
        print("Prediction:", pred["hybrid_risk_pct"], "% | Conformal:", pred["conformal_set"])

        gam_res = http_json(
            "POST",
            "/api/gamification/event",
            {
                "module": "Q-Quest",
                "action_type": "mission_completed",
                "item_id": pred["missions"][0]["id"],
                "outcome": "correct",
                "xp_earned": 75,
                "comprehension_score": 1.0,
                "details": "Verification mission",
                "mark_mission_id": pred["missions"][0]["id"],
            },
        )
        assert gam_res["gamification"]["xp"] == 75

        http_json(
            "POST",
            "/api/excel/users",
            {
                "gender": "Female",
                "age": 59,
                "hypertension": 1,
                "heart_disease": 0,
                "ever_married": "Yes",
                "work_type": "Private",
                "Residence_type": "Urban",
                "avg_glucose_level": 175.0,
                "bmi": 28.4,
                "smoking_status": "never smoked",
                "stroke": 0,
            },
        )

        # Wait for background auto-save loop (1.2s debounce) without calling sync-now
        time.sleep(2.5)
        st = http_json("GET", "/api/excel/status")
        print("Auto-sync status:", st["status"], "| dirty:", st["dirty"], "| save_count:", st["save_count"])
        assert st["dirty"] is False, f"Expected dirty=False, got {st}"
        assert st["sheet_counts"]["Users_Dataset"] == 5001
        assert st["sheet_counts"]["Predictions_Log"] == 2
        assert st["sheet_counts"]["Interaction_Telemetry"] == 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()

    wb = load_workbook(WORKBOOK_PATH, read_only=True)
    assert set(wb.sheetnames) == {
        "Users_Dataset",
        "Predictions_Log",
        "Gamification_Progress",
        "Interaction_Telemetry",
        "Model_Benchmarks",
    }
    users_rows = sum(1 for _ in wb["Users_Dataset"].iter_rows()) - 1
    preds_rows = sum(1 for _ in wb["Predictions_Log"].iter_rows()) - 1
    tel_rows = sum(1 for _ in wb["Interaction_Telemetry"].iter_rows()) - 1
    bench_rows = sum(1 for _ in wb["Model_Benchmarks"].iter_rows()) - 1
    wb.close()

    assert users_rows == 5001
    assert preds_rows == 2
    assert tel_rows == 1
    assert bench_rows == 7
    print("EXCEL ON-DISK VERIFIED:", users_rows, "users,", preds_rows, "predictions,", tel_rows, "telemetry,", bench_rows, "benchmarks.")

    # Reset to clean initial 5,000-user state? Let's keep clean initial workbook ready by removing test mutations:
    WORKBOOK_PATH.unlink()


if __name__ == "__main__":
    run_verification()
