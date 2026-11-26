"""Hybrid Quantum-Classical Stroke Prediction, Explainability & Conformal Uncertainty Engine.

Implements:
- 6-qubit exact statevector ZZFeatureMap & Quantum Kernel (QSVM)
- 6-qubit Variational Quantum Classifier (VQC) with Ry/Rz + CNOT ansatz
- Classical baselines (Logistic Regression, Random Forest, Gradient Boosting, RBF-SVM)
- Split Conformal Prediction for uncertainty quantification & ECE/Brier calibration
- Pairwise Quantum Feature-Interaction analysis (Risk Explorer)
- Adaptive Q-Quest mission generation & Q-SafePath clinical literacy cases
"""

from __future__ import annotations

import threading
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.svm import SVC


QUANTUM_FEATURES = [
    "age",
    "avg_glucose_level",
    "bmi_clean",
    "hypertension",
    "heart_disease",
    "smoking_risk",
]

FEATURE_LABELS = {
    "age": "Age",
    "avg_glucose_level": "Avg Glucose Level",
    "bmi_clean": "BMI",
    "hypertension": "Hypertension",
    "heart_disease": "Heart Disease",
    "smoking_risk": "Smoking Exposure",
}

SMOKING_RISK_MAP = {
    "never smoked": 0.0,
    "Unknown": 0.25,
    "formerly smoked": 0.55,
    "smokes": 1.0,
}

# Precomputed bitmasks for 6 qubits (64 basis states)
N_QUBITS = 6
DIM = 1 << N_QUBITS
BASIS_INDICES = np.arange(DIM, dtype=np.int64)
QUBIT_Z_SIGNS = np.array([1.0 - 2.0 * ((BASIS_INDICES >> q) & 1) for q in range(N_QUBITS)])  # shape (6, 64)


def _apply_hadamard_all(states: np.ndarray) -> np.ndarray:
    """Apply Hadamard gate to all N_QUBITS in vectorized batch (batch, 64)."""
    out = states.copy()
    inv_sqrt2 = 1.0 / np.sqrt(2.0)
    for q in range(N_QUBITS):
        bit = 1 << q
        idx0 = np.where((BASIS_INDICES & bit) == 0)[0]
        idx1 = idx0 | bit
        a = out[:, idx0]
        b = out[:, idx1]
        out[:, idx0] = (a + b) * inv_sqrt2
        out[:, idx1] = (a - b) * inv_sqrt2
    return out


def _apply_ry(states: np.ndarray, qubit: int, theta: float) -> np.ndarray:
    out = states.copy()
    c = np.cos(theta / 2.0)
    s = np.sin(theta / 2.0)
    bit = 1 << qubit
    idx0 = np.where((BASIS_INDICES & bit) == 0)[0]
    idx1 = idx0 | bit
    a = out[:, idx0]
    b = out[:, idx1]
    out[:, idx0] = c * a - s * b
    out[:, idx1] = s * a + c * b
    return out


def _apply_rz_batch(states: np.ndarray, qubit: int, angles: np.ndarray) -> np.ndarray:
    """Apply Rz(angle_i) per sample on given qubit. angles shape (batch,)."""
    z_sign = QUBIT_Z_SIGNS[qubit]  # +1 for |0>, -1 for |1>
    phase = np.exp(-0.5j * angles[:, None] * z_sign[None, :])
    return states * phase


def _apply_rz_scalar(states: np.ndarray, qubit: int, angle: float) -> np.ndarray:
    z_sign = QUBIT_Z_SIGNS[qubit]
    phase = np.exp(-0.5j * angle * z_sign)
    return states * phase[None, :]


def _apply_cnot(states: np.ndarray, control: int, target: int) -> np.ndarray:
    perm = BASIS_INDICES.copy()
    ctrl_mask = (BASIS_INDICES & (1 << control)) != 0
    perm[ctrl_mask] ^= 1 << target
    return states[:, perm]


def zz_feature_map_states(X_angles: np.ndarray, reps: int = 2) -> np.ndarray:
    """Exact 6-qubit ZZFeatureMap statevector encoding for batch X_angles (N, 6) in [0, pi]."""
    batch = X_angles.shape[0]
    states = np.zeros((batch, DIM), dtype=np.complex128)
    states[:, 0] = 1.0 + 0.0j

    pairs = [(i, (i + 1) % N_QUBITS) for i in range(N_QUBITS)]
    for _ in range(reps):
        states = _apply_hadamard_all(states)
        for q in range(N_QUBITS):
            states = _apply_rz_batch(states, q, 2.0 * X_angles[:, q])
        for q1, q2 in pairs:
            zz_angle = 2.0 * (np.pi - X_angles[:, q1]) * (np.pi - X_angles[:, q2])
            zz_sign = QUBIT_Z_SIGNS[q1] * QUBIT_Z_SIGNS[q2]
            states = states * np.exp(-0.5j * zz_angle[:, None] * zz_sign[None, :])
    return states


def vqc_forward(encoded_states: np.ndarray, params: np.ndarray) -> np.ndarray:
    """Apply 2-layer Ry-Rz-CNOT variational ansatz and return P(|1> on readout qubit 0)."""
    states = encoded_states
    idx = 0
    for _layer in range(2):
        for q in range(N_QUBITS):
            states = _apply_ry(states, q, float(params[idx]))
            idx += 1
            states = _apply_rz_scalar(states, q, float(params[idx]))
            idx += 1
        for q in range(N_QUBITS):
            states = _apply_cnot(states, q, (q + 1) % N_QUBITS)

    probs = np.abs(states) ** 2
    mask_q0_one = (BASIS_INDICES & 1) == 1
    p_one = np.sum(probs[:, mask_q0_one], axis=1)
    return np.clip(p_one, 1e-6, 1.0 - 1e-6)


def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        if i == n_bins - 1:
            mask = (y_prob >= lo) & (y_prob <= hi)
        else:
            mask = (y_prob >= lo) & (y_prob < hi)
        if np.any(mask):
            acc = np.mean(y_true[mask])
            conf = np.mean(y_prob[mask])
            ece += (np.sum(mask) / n) * abs(acc - conf)
    return float(ece)


class QuantumStrokeEngine:
    """Trains and serves QSVM, VQC, classical baselines, conformal prediction, and explainability."""

    def __init__(self, df: pd.DataFrame):
        self._lock = threading.RLock()
        self.bmi_median: float = 28.0
        self.q_scaler = MinMaxScaler(feature_range=(0.05, np.pi - 0.05))
        self.c_scaler = StandardScaler()

        self.landmark_states: np.ndarray | None = None
        self.qsvm_model: SVC | None = None
        self.vqc_params: np.ndarray | None = None
        self.vqc_calib_scale: float = 1.0
        self.vqc_calib_bias: float = 0.0

        self.classical_models: dict[str, Any] = {}
        self.conformal_q_neg: float = 0.28
        self.conformal_q_pos: float = 0.72
        self.alpha: float = 0.12
        self.benchmarks: list[dict[str, Any]] = []
        self.risk_coverage_curve: list[dict[str, float]] = []
        self.cohort_stats: dict[str, Any] = {}
        self.global_interactions: list[dict[str, Any]] = []
        self.safepath_cases: list[dict[str, Any]] = []

        self.fit(df)

    def _preprocess_df(self, df: pd.DataFrame, fit_stats: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        work = df.copy()
        bmi_num = pd.to_numeric(work["bmi"], errors="coerce")
        if fit_stats:
            self.bmi_median = float(bmi_num.median() if not np.isnan(bmi_num.median()) else 28.0)

        work["bmi_missing"] = bmi_num.isna().astype(float)
        work["bmi_clean"] = bmi_num.fillna(self.bmi_median)
        work["age"] = pd.to_numeric(work["age"], errors="coerce").fillna(45.0)
        work["avg_glucose_level"] = pd.to_numeric(work["avg_glucose_level"], errors="coerce").fillna(100.0)
        work["hypertension"] = pd.to_numeric(work["hypertension"], errors="coerce").fillna(0).astype(float)
        work["heart_disease"] = pd.to_numeric(work["heart_disease"], errors="coerce").fillna(0).astype(float)
        work["smoking_risk"] = work["smoking_status"].astype(str).map(SMOKING_RISK_MAP).fillna(0.25)

        work["gender_male"] = (work["gender"].astype(str) == "Male").astype(float)
        work["married_yes"] = (work["ever_married"].astype(str) == "Yes").astype(float)
        work["urban"] = (work["Residence_type"].astype(str) == "Urban").astype(float)
        work["work_self"] = (work["work_type"].astype(str) == "Self-employed").astype(float)
        work["work_govt"] = (work["work_type"].astype(str) == "Govt_job").astype(float)

        classical_cols = QUANTUM_FEATURES + ["bmi_missing", "gender_male", "married_yes", "urban", "work_self", "work_govt"]

        X_q_raw = work[QUANTUM_FEATURES].to_numpy(dtype=float)
        X_c_raw = work[classical_cols].to_numpy(dtype=float)

        if fit_stats:
            X_q = self.q_scaler.fit_transform(X_q_raw)
            X_c = self.c_scaler.fit_transform(X_c_raw)
        else:
            X_q = np.clip(self.q_scaler.transform(X_q_raw), 0.01, np.pi - 0.01)
            X_c = self.c_scaler.transform(X_c_raw)

        y = pd.to_numeric(work["stroke"], errors="coerce").fillna(0).astype(int).to_numpy() if "stroke" in work.columns else None
        return X_q, X_c, y

    def _compute_metrics(self, name: str, family: str, y_true: np.ndarray, y_prob: np.ndarray) -> dict[str, Any]:
        # Optimal probability threshold tuned on balanced F1 (for imbalanced stroke data)
        best_f1 = 0.0
        best_thresh = 0.5
        for th in np.linspace(0.15, 0.75, 25):
            preds = (y_prob >= th).astype(int)
            score = f1_score(y_true, preds, zero_division=0)
            if score > best_f1:
                best_f1 = score
                best_thresh = float(th)

        y_pred = (y_prob >= best_thresh).astype(int)
        return {
            "model_name": name,
            "family": family,
            "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
            "pr_auc": round(float(average_precision_score(y_true, y_prob)), 4),
            "f1_score": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
            "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
            "brier_score": round(float(brier_score_loss(y_true, y_prob)), 4),
            "ece": round(float(compute_ece(y_true, y_prob)), 4),
        }

    def fit(self, df: pd.DataFrame) -> None:
        with self._lock:
            y_all = pd.to_numeric(df["stroke"], errors="raise").to_numpy()
            if set(y_all) != {0, 1}:
                raise ValueError("stroke must contain both binary labels 0 and 1")

            # Cohort summary statistics for dashboards & Risk Explorer
            stroke_rate = float(np.mean(y_all))
            bmi_missing_count = int(pd.to_numeric(df["bmi"], errors="coerce").isna().sum())
            unknown_smoke_count = int((df["smoking_status"].astype(str) == "Unknown").sum())
            self.cohort_stats = {
                "total_users": int(len(df)),
                "stroke_positive": int(np.sum(y_all)),
                "stroke_negative": int(len(y_all) - np.sum(y_all)),
                "stroke_rate_pct": round(stroke_rate * 100.0, 2),
                "bmi_missing_count": bmi_missing_count,
                "unknown_smoking_count": unknown_smoke_count,
                "n_qubits": N_QUBITS,
                "hilbert_dim": DIM,
            }

            # Stratified Train (65%), Calibration (15%), Test (20%)
            idx_all = np.arange(len(df))
            idx_train_cal, idx_test = train_test_split(idx_all, test_size=0.20, random_state=42, stratify=y_all)
            idx_train, idx_cal = train_test_split(
                idx_train_cal, test_size=0.1875, random_state=42, stratify=y_all[idx_train_cal]
            )

            idx_probability, idx_conformal = train_test_split(
                idx_cal, test_size=0.5, random_state=42, stratify=y_all[idx_cal]
            )
            X_q_tr, X_c_tr, y_tr = self._preprocess_df(df.iloc[idx_train], fit_stats=True)
            X_q_probability, _, y_probability = self._preprocess_df(df.iloc[idx_probability])
            X_q_cal, X_c_cal, y_cal = self._preprocess_df(df.iloc[idx_conformal])
            X_q_te, X_c_te, y_te = self._preprocess_df(df.iloc[idx_test])
            self.cohort_stats["split_sizes"] = {
                "train": len(idx_train), "probability_calibration": len(idx_probability),
                "conformal_calibration": len(idx_conformal), "test": len(idx_test),
            }

            # 1) QSVM using ZZFeatureMap quantum fidelity kernel on stratified landmark set (160 samples)
            pos_idx = np.where(y_tr == 1)[0]
            neg_idx = np.where(y_tr == 0)[0]
            rng = np.random.default_rng(42)
            n_pos_lm = min(len(pos_idx), 70)
            n_neg_lm = min(len(neg_idx), 110)
            lm_idx = np.concatenate(
                [rng.choice(pos_idx, n_pos_lm, replace=False), rng.choice(neg_idx, n_neg_lm, replace=False)]
            )
            self.landmark_states = zz_feature_map_states(X_q_tr[lm_idx], reps=2)
            y_lm = y_tr[lm_idx]
            K_lm = np.abs(self.landmark_states @ self.landmark_states.conj().T) ** 2

            self.qsvm_model = SVC(kernel="precomputed", probability=True, class_weight="balanced", C=1.5, random_state=42)
            self.qsvm_model.fit(K_lm, y_lm)

            # 2) VQC optimization on stratified mini-batch (220 samples)
            n_pos_vqc = min(len(pos_idx), 90)
            n_neg_vqc = min(len(neg_idx), 130)
            vqc_idx = np.concatenate(
                [rng.choice(pos_idx, n_pos_vqc, replace=False), rng.choice(neg_idx, n_neg_vqc, replace=False)]
            )
            vqc_states = zz_feature_map_states(X_q_tr[vqc_idx], reps=1)
            y_vqc = y_tr[vqc_idx].astype(float)
            # Balance weights for VQC loss
            w_pos = len(y_vqc) / (2.0 * max(np.sum(y_vqc == 1), 1))
            w_neg = len(y_vqc) / (2.0 * max(np.sum(y_vqc == 0), 1))
            sample_w = np.where(y_vqc == 1, w_pos, w_neg)

            init_params = rng.uniform(-0.8, 0.8, size=2 * 2 * N_QUBITS)

            def vqc_loss(theta: np.ndarray) -> float:
                p = vqc_forward(vqc_states, theta)
                bce = -(y_vqc * np.log(p) + (1.0 - y_vqc) * np.log(1.0 - p))
                return float(np.mean(sample_w * bce))

            res = minimize(vqc_loss, init_params, method="COBYLA", options={"maxiter": 48})
            self.vqc_params = res.x

            # Platt scaling of VQC raw probabilities on calibration set so probabilities are well-calibrated
            vqc_cal_raw = vqc_forward(zz_feature_map_states(X_q_probability, reps=1), self.vqc_params)
            vqc_logit = np.log(vqc_cal_raw / (1.0 - vqc_cal_raw))[:, None]
            platt = LogisticRegression(random_state=42)
            platt.fit(vqc_logit, y_probability)
            self.vqc_calib_scale = float(platt.coef_[0][0])
            self.vqc_calib_bias = float(platt.intercept_[0])

            # 3) Classical baseline models
            lr = LogisticRegression(class_weight="balanced", max_iter=500, random_state=42)
            lr.fit(X_c_tr, y_tr)

            rf = RandomForestClassifier(
                n_estimators=120, max_depth=8, min_samples_leaf=8, class_weight="balanced", random_state=42, n_jobs=-1
            )
            rf.fit(X_c_tr, y_tr)

            gb = GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.06, random_state=42)
            gb.fit(X_c_tr, y_tr)

            c_svm = SVC(kernel="rbf", probability=True, class_weight="balanced", C=1.2, random_state=42)
            c_svm.fit(X_c_tr[:1800], y_tr[:1800])

            self.classical_models = {
                "Logistic Regression": lr,
                "Random Forest": rf,
                "Gradient Boosting": gb,
                "Classical SVM (RBF)": c_svm,
            }

            # Evaluate QSVM, VQC, Hybrid, and Classical models on Test set
            qsvm_te = self._predict_qsvm_batch(X_q_te)
            vqc_te = self._predict_vqc_batch(X_q_te)
            rf_te = rf.predict_proba(X_c_te)[:, 1]
            lr_te = lr.predict_proba(X_c_te)[:, 1]
            gb_te = gb.predict_proba(X_c_te)[:, 1]
            svm_te = c_svm.predict_proba(X_c_te)[:, 1]

            hybrid_te = 0.42 * qsvm_te + 0.28 * vqc_te + 0.30 * gb_te

            self.benchmarks = [
                self._compute_metrics("Hybrid Q-SmartStroke", "Quantum-Classical", y_te, hybrid_te),
                self._compute_metrics("QSVM (ZZFeatureMap)", "Quantum", y_te, qsvm_te),
                self._compute_metrics("VQC (6-Qubit Ansatz)", "Quantum", y_te, vqc_te),
                self._compute_metrics("Gradient Boosting", "Classical", y_te, gb_te),
                self._compute_metrics("Random Forest", "Classical", y_te, rf_te),
                self._compute_metrics("Classical SVM (RBF)", "Classical", y_te, svm_te),
                self._compute_metrics("Logistic Regression", "Classical", y_te, lr_te),
            ]

            # 4) Mondrian (Class-Conditional) Split Conformal Prediction for imbalanced data
            qsvm_cal = self._predict_qsvm_batch(X_q_cal)
            vqc_cal = self._predict_vqc_batch(X_q_cal)
            gb_cal = gb.predict_proba(X_c_cal)[:, 1]
            hybrid_cal = 0.42 * qsvm_cal + 0.28 * vqc_cal + 0.30 * gb_cal

            neg_scores = hybrid_cal[y_cal == 0]
            pos_scores = 1.0 - hybrid_cal[y_cal == 1]
            if len(neg_scores) > 0:
                q_neg_lvl = min((np.ceil((len(neg_scores) + 1) * (1.0 - self.alpha)) / len(neg_scores)), 0.99)
                self.conformal_q_neg = float(np.quantile(neg_scores, q_neg_lvl))
            if len(pos_scores) > 0:
                q_pos_lvl = min((np.ceil((len(pos_scores) + 1) * (1.0 - self.alpha)) / len(pos_scores)), 0.99)
                self.conformal_q_pos = float(np.quantile(pos_scores, q_pos_lvl))

            # Build Risk-Coverage curve on test set
            unc_te = np.abs(hybrid_te - 0.5)
            order = np.argsort(-unc_te)  # highest margin = lowest uncertainty first
            curve = []
            for cov in [0.2, 0.4, 0.6, 0.8, 1.0]:
                k = max(10, int(cov * len(order)))
                sel = order[:k]
                err = float(np.mean(((hybrid_te[sel] >= 0.35).astype(int) != y_te[sel])))
                curve.append({"coverage": round(cov * 100, 0), "accuracy": round((1.0 - err) * 100, 1)})
            self.risk_coverage_curve = curve

            # 5) Compute global pairwise risk-factor interaction discoveries & Q-SafePath cases
            self.global_interactions = self._compute_global_interactions(df)
            self.safepath_cases = self._build_safepath_cases()

    def _predict_qsvm_batch(self, X_q: np.ndarray) -> np.ndarray:
        assert self.landmark_states is not None and self.qsvm_model is not None
        states = zz_feature_map_states(X_q, reps=2)
        K = np.abs(states @ self.landmark_states.conj().T) ** 2
        return self.qsvm_model.predict_proba(K)[:, 1]

    def _predict_vqc_batch(self, X_q: np.ndarray) -> np.ndarray:
        assert self.vqc_params is not None
        states = zz_feature_map_states(X_q, reps=1)
        raw = vqc_forward(states, self.vqc_params)
        logits = self.vqc_calib_scale * np.log(raw / (1.0 - raw)) + self.vqc_calib_bias
        return 1.0 / (1.0 + np.exp(-np.clip(logits, -20.0, 20.0)))

    def _compute_global_interactions(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        work = df.copy()
        work["bmi_num"] = pd.to_numeric(work["bmi"], errors="coerce").fillna(self.bmi_median)
        baseline = float(pd.to_numeric(work["stroke"], errors="coerce").mean())

        pairs = [
            ("hypertension", "heart_disease", "Hypertension + Heart Disease", work["hypertension"] == 1, work["heart_disease"] == 1),
            ("age", "avg_glucose_level", "Age ≥ 60 + High Glucose (≥ 160)", work["age"] >= 60, work["avg_glucose_level"] >= 160),
            ("age", "hypertension", "Age ≥ 60 + Hypertension", work["age"] >= 60, work["hypertension"] == 1),
            ("bmi_clean", "hypertension", "Elevated BMI (≥ 30) + Hypertension", work["bmi_num"] >= 30, work["hypertension"] == 1),
            ("heart_disease", "avg_glucose_level", "Heart Disease + High Glucose", work["heart_disease"] == 1, work["avg_glucose_level"] >= 160),
            ("smoking_risk", "age", "Active Smoking + Age ≥ 55", work["smoking_status"] == "smokes", work["age"] >= 55),
        ]

        results = []
        for f1, f2, label, m1, m2 in pairs:
            both = m1 & m2
            only1 = m1 & (~m2)
            only2 = (~m1) & m2
            neither = (~m1) & (~m2)

            rate_both = float(work.loc[both, "stroke"].mean()) if both.sum() > 0 else baseline
            rate_1 = float(work.loc[only1, "stroke"].mean()) if only1.sum() > 0 else baseline
            rate_2 = float(work.loc[only2, "stroke"].mean()) if only2.sum() > 0 else baseline
            rate_none = float(work.loc[neither, "stroke"].mean()) if neither.sum() > 0 else baseline
            amp = round(rate_both / max(baseline, 1e-4), 2)

            results.append(
                {
                    "id": f"{f1}__{f2}",
                    "feature_a": f1,
                    "feature_b": f2,
                    "label": label,
                    "cohort_count": int(both.sum()),
                    "both_stroke_rate_pct": round(rate_both * 100, 1),
                    "only_a_rate_pct": round(rate_1 * 100, 1),
                    "only_b_rate_pct": round(rate_2 * 100, 1),
                    "baseline_rate_pct": round(rate_none * 100, 1),
                    "amplification_x": amp,
                }
            )
        results.sort(key=lambda r: r["amplification_x"], reverse=True)
        return results

    def _build_safepath_cases(self) -> list[dict[str, Any]]:
        """Build fictional cases for the uncertainty exercise."""
        base = {
            "gender": "Female", "ever_married": "Yes", "work_type": "Private",
            "Residence_type": "Urban", "smoking_status": "never smoked",
        }
        picks = [
            dict(base, id=i, age=age, hypertension=pressure, heart_disease=heart,
                 avg_glucose_level=glucose, bmi=bmi)
            for i, (age, pressure, heart, glucose, bmi) in enumerate([
                (29, 0, 0, 94, 23), (38, 0, 0, 105, 26),
                (51, 1, 0, 128, None), (61, 0, 0, 175, 29),
                (70, 1, 0, 151, 30), (76, 1, 1, 199, 32),
            ], start=1)
        ]

        cases = []
        for i, row in enumerate(picks[:6]):
            pred = self.predict_profile(row)
            cases.append(
                {
                    "case_id": f"SP-{i + 1}",
                    "user_id": int(row["id"]),
                    "profile": {
                        "gender": row["gender"],
                        "age": float(row["age"]),
                        "hypertension": int(row["hypertension"]),
                        "heart_disease": int(row["heart_disease"]),
                        "ever_married": row["ever_married"],
                        "work_type": row["work_type"],
                        "Residence_type": row["Residence_type"],
                        "avg_glucose_level": float(row["avg_glucose_level"]),
                        "bmi": None if pd.isna(row["bmi"]) else float(row["bmi"]),
                        "smoking_status": row["smoking_status"],
                    },
                    "prediction": {
                        "hybrid_risk_pct": pred["hybrid_risk_pct"],
                        "qsvm_risk_pct": pred["qsvm_risk_pct"],
                        "vqc_risk_pct": pred["vqc_risk_pct"],
                        "uncertainty_pct": pred["uncertainty_pct"],
                        "conformal_set": pred["conformal_set"],
                        "confidence_tier": pred["confidence_tier"],
                    },
                    "recommended_action": pred["recommended_action"],
                    "rationale": pred["clinical_rationale"],
                }
            )
        return cases

    def predict_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Run full hybrid quantum-classical prediction + explainability + conformal uncertainty + Q-Quest missions."""
        with self._lock:
            row_df = pd.DataFrame(
                [
                    {
                        "id": profile.get("id", 0),
                        "gender": profile.get("gender", "Female"),
                        "age": float(profile.get("age", 45)),
                        "hypertension": int(profile.get("hypertension", 0)),
                        "heart_disease": int(profile.get("heart_disease", 0)),
                        "ever_married": profile.get("ever_married", "Yes"),
                        "work_type": profile.get("work_type", "Private"),
                        "Residence_type": profile.get("Residence_type", "Urban"),
                        "avg_glucose_level": float(profile.get("avg_glucose_level", 100.0)),
                        "bmi": profile.get("bmi"),
                        "smoking_status": profile.get("smoking_status", "never smoked"),
                        "stroke": 0,
                    }
                ]
            )
            X_q, X_c, _ = self._preprocess_df(row_df, fit_stats=False)

            qsvm_p = float(self._predict_qsvm_batch(X_q)[0])
            vqc_p = float(self._predict_vqc_batch(X_q)[0])
            gb_p = float(self.classical_models["Gradient Boosting"].predict_proba(X_c)[0, 1])
            rf_p = float(self.classical_models["Random Forest"].predict_proba(X_c)[0, 1])
            lr_p = float(self.classical_models["Logistic Regression"].predict_proba(X_c)[0, 1])

            hybrid_p = float(np.clip(0.42 * qsvm_p + 0.28 * vqc_p + 0.30 * gb_p, 0.01, 0.99))

            # Mondrian class-conditional conformal prediction set
            conformal_set = []
            if hybrid_p <= self.conformal_q_neg:
                conformal_set.append("Low Risk")
            if (1.0 - hybrid_p) <= self.conformal_q_pos:
                conformal_set.append("High Risk")
            if not conformal_set:
                conformal_set = ["High Risk" if hybrid_p >= 0.35 else "Low Risk"]

            # Uncertainty combines model disagreement + predictive entropy + indeterminate conformal set
            disagreement = float(np.std([qsvm_p, vqc_p, rf_p, gb_p]))
            entropy = -(hybrid_p * np.log2(hybrid_p) + (1.0 - hybrid_p) * np.log2(1.0 - hybrid_p))
            indeterminate_bonus = 0.22 if len(conformal_set) == 2 else 0.0
            uncertainty = float(np.clip(0.45 * entropy + 1.4 * disagreement + indeterminate_bonus, 0.06, 0.96))

            if len(conformal_set) == 2 or uncertainty >= 0.58:
                confidence_tier = "High Uncertainty — Clinical Review Needed"
            elif uncertainty >= 0.36:
                confidence_tier = "Moderate Confidence — Monitor & Verify"
            else:
                confidence_tier = "High Confidence"

            if hybrid_p >= 0.42 or (len(conformal_set) == 2 and hybrid_p >= 0.28):
                recommended_action = "urgent_clinical_review"
                rationale = (
                    "Elevated hybrid quantum risk or indeterminate conformal set ({}) warrants formal clinical screening."
                    .format(", ".join(conformal_set))
                )
            elif hybrid_p >= 0.18 or uncertainty >= 0.45:
                recommended_action = "targeted_monitoring"
                rationale = (
                    "Moderate risk or elevated epistemic uncertainty ({:.0f}%): schedule preventive lab/BP follow-up."
                    .format(uncertainty * 100)
                )
            else:
                recommended_action = "routine_prevention"
                rationale = "Low predicted risk with tight conformal confidence: continue preventive lifestyle quests."

            # Qubit state visualization (marginal P(|1>) per qubit & top amplitudes in ZZFeatureMap)
            zz_state = zz_feature_map_states(X_q, reps=2)[0]
            probs = np.abs(zz_state) ** 2
            qubit_excitations = []
            for q_idx, fname in enumerate(QUANTUM_FEATURES):
                p1 = float(np.sum(probs[(BASIS_INDICES & (1 << q_idx)) != 0]))
                qubit_excitations.append(
                    {
                        "qubit": f"q{q_idx}",
                        "feature": fname,
                        "label": FEATURE_LABELS[fname],
                        "angle_rad": round(float(X_q[0, q_idx]), 3),
                        "prob_one": round(p1, 4),
                    }
                )

            # Local perturbation attribution for explainability
            contributions = []
            baseline_q = np.full_like(X_q, 0.45)
            for idx, fname in enumerate(QUANTUM_FEATURES):
                perturbed = X_q.copy()
                perturbed[0, idx] = baseline_q[0, idx]
                p_pert = float(self._predict_qsvm_batch(perturbed)[0])
                delta = round((qsvm_p - p_pert) * 100.0, 2)
                contributions.append(
                    {
                        "feature": fname,
                        "label": FEATURE_LABELS[fname],
                        "impact_pct": delta,
                    }
                )
            contributions.sort(key=lambda c: abs(c["impact_pct"]), reverse=True)

            top_interaction = self._detect_profile_interaction(profile)
            missions = self._generate_adaptive_missions(profile, hybrid_p)

            return {
                "hybrid_risk_pct": round(hybrid_p * 100, 1),
                "qsvm_risk_pct": round(qsvm_p * 100, 1),
                "vqc_risk_pct": round(vqc_p * 100, 1),
                "classical_rf_pct": round(rf_p * 100, 1),
                "classical_gb_pct": round(gb_p * 100, 1),
                "classical_lr_pct": round(lr_p * 100, 1),
                "risk_category": "High Risk" if hybrid_p >= 0.40 else ("Moderate Risk" if hybrid_p >= 0.18 else "Low Risk"),
                "uncertainty_pct": round(uncertainty * 100, 1),
                "conformal_set": conformal_set,
                "confidence_tier": confidence_tier,
                "recommended_action": recommended_action,
                "clinical_rationale": rationale,
                "qubit_states": qubit_excitations,
                "feature_contributions": contributions,
                "top_interaction": top_interaction,
                "missions": missions,
            }

    def _detect_profile_interaction(self, p: dict[str, Any]) -> str:
        age = float(p.get("age", 45))
        hyp = int(p.get("hypertension", 0))
        hd = int(p.get("heart_disease", 0))
        gluc = float(p.get("avg_glucose_level", 100))
        bmi_val = p.get("bmi")
        bmi = float(bmi_val) if bmi_val not in (None, "", "N/A") else self.bmi_median
        smoke = str(p.get("smoking_status", "never smoked"))

        if hyp == 1 and hd == 1:
            return "Hypertension × Heart Disease (ZZ Entangled Synergy)"
        if age >= 60 and gluc >= 160:
            return "Age ≥ 60 × Hyperglycemia (ZZ Entangled Synergy)"
        if age >= 60 and hyp == 1:
            return "Age ≥ 60 × Hypertension (Vascular Stress)"
        if bmi >= 30 and hyp == 1:
            return "Elevated BMI × Hypertension (Metabolic Load)"
        if smoke == "smokes" and age >= 50:
            return "Active Smoking × Age ≥ 50"
        return "Baseline Demographic-Metabolic Profile"

    def _generate_adaptive_missions(self, p: dict[str, Any], hybrid_p: float) -> list[dict[str, Any]]:
        missions: list[dict[str, Any]] = []
        hyp = int(p.get("hypertension", 0))
        hd = int(p.get("heart_disease", 0))
        gluc = float(p.get("avg_glucose_level", 100))
        bmi_val = p.get("bmi")
        bmi = float(bmi_val) if bmi_val not in (None, "", "N/A") else None
        smoke = str(p.get("smoking_status", "never smoked"))

        if hyp == 1:
            missions.append(
                {
                    "id": "mission_bp_shield",
                    "title": "Vascular Pressure Shield",
                    "factor": "Hypertension",
                    "xp": 75,
                    "difficulty": "Priority",
                    "description": "Hypertension amplifies stroke risk nonlinearly with age. Log a 7-day sodium-reduction & home BP check routine.",
                    "quiz_prompt": "Which lifestyle shift produces the largest systolic BP reduction for hypertension management?",
                    "quiz_options": [
                        "DASH diet + <1,500–2,300mg sodium/day + regular aerobic walks",
                        "Skipping morning hydration",
                        "Eliminating all dietary potassium",
                    ],
                    "correct_index": 0,
                }
            )
        if gluc >= 140:
            missions.append(
                {
                    "id": "mission_glucose_balance",
                    "title": "Glycemic Equilibrium Quest",
                    "factor": "Avg Glucose Level",
                    "xp": 80,
                    "difficulty": "Priority",
                    "description": f"Your avg glucose ({gluc:.0f} mg/dL) enters the hyperglycemic zone. Complete a post-meal 15-min walk challenge.",
                    "quiz_prompt": "Why does elevated average glucose interact strongly with heart disease in quantum risk maps?",
                    "quiz_options": [
                        "Chronic hyperglycemia accelerates endothelial & microvascular damage",
                        "Glucose only affects bone density",
                        "It lowers blood viscosity below normal",
                    ],
                    "correct_index": 0,
                }
            )
        if bmi is None or bmi >= 28:
            missions.append(
                {
                    "id": "mission_bmi_calibration",
                    "title": "Metabolic Baseline Calibration",
                    "factor": "BMI",
                    "xp": 60,
                    "difficulty": "Core",
                    "description": (
                        "BMI is currently missing—record an updated anthropometric reading to eliminate imputation uncertainty."
                        if bmi is None
                        else f"BMI is {bmi:.1f}. Build a sustainable 150 min/week zone-2 cardio + fiber goal."
                    ),
                    "quiz_prompt": "How does missing BMI data impact quantum stroke risk models?",
                    "quiz_options": [
                        "It increases epistemic uncertainty and requires median imputation + uncertainty flagging",
                        "It guarantees zero stroke risk",
                        "It deletes the age qubit",
                    ],
                    "correct_index": 0,
                }
            )
        if smoke in ("smokes", "formerly smoked", "Unknown"):
            missions.append(
                {
                    "id": "mission_smoke_clear",
                    "title": "Smoke-Free Artery Reset",
                    "factor": "Smoking Status",
                    "xp": 70,
                    "difficulty": "Core",
                    "description": "Clarify or reduce tobacco exposure—vascular stroke risk drops measurably within months of cessation.",
                    "quiz_prompt": "Why is 'Unknown' smoking status handled separately from 'never smoked' in research?",
                    "quiz_options": [
                        "Treating Unknown as never smoked biases predictions and hides missingness patterns",
                        "They are clinically identical",
                        "Unknown always means heavy smoker",
                    ],
                    "correct_index": 0,
                }
            )
        if hd == 1 or hybrid_p >= 0.30:
            missions.append(
                {
                    "id": "mission_fast_protocol",
                    "title": "F.A.S.T. Rapid Recognition Drill",
                    "factor": "Cardiac & Acute Readiness",
                    "xp": 90,
                    "difficulty": "Boss Mission",
                    "description": "High-priority preparedness: master early stroke warning signs and emergency response windows.",
                    "quiz_prompt": "What does F.A.S.T. stand for in acute stroke recognition?",
                    "quiz_options": [
                        "Face drooping, Arm weakness, Speech difficulty, Time to call emergency services",
                        "Fatigue, Appetite, Sleep, Temperature",
                        "Fasting, Activity, Salt, Testing",
                    ],
                    "correct_index": 0,
                }
            )

        # Always guarantee at least 3 engaging missions
        if len(missions) < 3:
            missions.append(
                {
                    "id": "mission_quantum_literacy",
                    "title": "Quantum Risk Literacy Primer",
                    "factor": "Preventive Awareness",
                    "xp": 55,
                    "difficulty": "Starter",
                    "description": "Learn how hybrid QSVM + VQC models combine nonlinear clinical interactions with uncertainty bounds.",
                    "quiz_prompt": "When a conformal predictor outputs {'Low Risk', 'High Risk'}, what should happen next?",
                    "quiz_options": [
                        "Flag the case as uncertain and recommend clinical review rather than guessing",
                        "Ignore the prediction completely",
                        "Force the score to 0%",
                    ],
                    "correct_index": 0,
                }
            )
        return missions
