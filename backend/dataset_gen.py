"""Synthetic 5,000-user stroke risk dataset generator matching the 12-column schema."""

from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = [
    "id",
    "gender",
    "age",
    "hypertension",
    "heart_disease",
    "ever_married",
    "work_type",
    "Residence_type",
    "avg_glucose_level",
    "bmi",
    "smoking_status",
    "stroke",
]


def generate_stroke_dataset(n_users: int = 5000, seed: int = 42) -> pd.DataFrame:
    """Generate a realistic 5,000-user tabular dataset with 12 stroke-risk columns.

    Includes realistic missing BMI (~3.5%), Unknown smoking status (~26%),
    class imbalance (~5% stroke-positive), and nonlinear feature interactions.
    """
    rng = np.random.default_rng(seed)

    ids = np.arange(1001, 1001 + n_users)
    gender = rng.choice(["Female", "Male", "Other"], size=n_users, p=[0.585, 0.413, 0.002])

    # Age distribution skewed toward adults/older adults
    age = np.clip(rng.normal(loc=43.5, scale=22.0, size=n_users), 1.0, 82.0)
    age = np.round(age, 1)
    # Keep integers for adults >= 2, 1-decimal for infants
    age = np.where(age >= 2.0, np.round(age, 0), np.round(age, 2))

    ever_married = np.where(
        age < 18,
        "No",
        rng.choice(["Yes", "No"], size=n_users, p=[0.78, 0.22]),
    )
    # Adjust married probability slightly by age
    married_prob = 1.0 / (1.0 + np.exp(-(age - 26.0) / 5.5))
    ever_married = np.where(rng.random(n_users) < married_prob, "Yes", "No")

    work_type = np.empty(n_users, dtype=object)
    for i in range(n_users):
        a = age[i]
        if a < 16:
            work_type[i] = "children"
        elif a < 22:
            work_type[i] = rng.choice(["Private", "Never_worked", "Self-employed"], p=[0.72, 0.20, 0.08])
        elif a > 65:
            work_type[i] = rng.choice(["Self-employed", "Private", "Govt_job"], p=[0.42, 0.38, 0.20])
        else:
            work_type[i] = rng.choice(["Private", "Self-employed", "Govt_job", "Never_worked"], p=[0.61, 0.19, 0.18, 0.02])

    residence_type = rng.choice(["Urban", "Rural"], size=n_users, p=[0.51, 0.49])

    # Medical risk factors correlated with age
    hyp_logit = -4.2 + 0.048 * age + rng.normal(0, 0.65, n_users)
    hypertension = (rng.random(n_users) < (1.0 / (1.0 + np.exp(-hyp_logit)))).astype(int)

    hd_logit = -5.3 + 0.052 * age + 0.75 * hypertension + rng.normal(0, 0.6, n_users)
    heart_disease = (rng.random(n_users) < (1.0 / (1.0 + np.exp(-hd_logit)))).astype(int)

    # Bimodal glucose distribution (normal vs hyperglycemic tail)
    is_elevated_glucose = rng.random(n_users) < (0.10 + 0.0035 * np.maximum(age - 30, 0) + 0.09 * hypertension)
    avg_glucose_level = np.where(
        is_elevated_glucose,
        rng.normal(loc=196.0, scale=32.0, size=n_users),
        rng.normal(loc=92.0, scale=18.0, size=n_users),
    )
    avg_glucose_level = np.round(np.clip(avg_glucose_level, 55.0, 272.0), 2)

    # BMI correlated with age & hypertension, with ~3.5% missing values
    bmi_base = 22.0 + 0.11 * np.minimum(age, 55.0) + 2.4 * hypertension + rng.normal(0, 5.8, n_users)
    bmi = np.round(np.clip(bmi_base, 13.5, 58.0), 1).astype(object)
    missing_bmi_mask = rng.random(n_users) < 0.036
    bmi[missing_bmi_mask] = np.nan

    # Smoking status with ~26% Unknown
    smoking_status = np.empty(n_users, dtype=object)
    for i in range(n_users):
        if age[i] < 14:
            smoking_status[i] = "Unknown"
        else:
            smoking_status[i] = rng.choice(
                ["never smoked", "Unknown", "formerly smoked", "smokes"],
                p=[0.40, 0.24, 0.19, 0.17],
            )

    # Nonlinear stroke risk logit (captures ZZ-style pairwise interactions for QML)
    z_age = (age - 45.0) / 20.0
    z_gluc = (avg_glucose_level - 106.0) / 45.0
    z_bmi = (pd.to_numeric(bmi, errors="coerce").astype(float) - 28.0) / 7.5
    z_bmi = np.nan_to_num(z_bmi, nan=0.4)

    smoke_risk = np.where(
        smoking_status == "smokes",
        0.55,
        np.where(smoking_status == "formerly smoked", 0.25, 0.0),
    )

    # Nonlinear interactions: age*hypertension, heart_disease*glucose, bmi*hypertension
    stroke_logit = (
        -4.95
        + 1.85 * z_age
        + 0.72 * hypertension
        + 0.85 * heart_disease
        + 0.58 * z_gluc
        + 0.22 * z_bmi
        + 0.42 * smoke_risk
        + 0.65 * (z_age * hypertension)
        + 0.55 * (heart_disease * np.maximum(z_gluc, 0.0))
        + 0.35 * (np.maximum(z_bmi, 0.0) * hypertension)
        + 0.30 * np.sin(1.2 * z_age * z_gluc)
        + rng.normal(0, 0.35, n_users)
    )
    stroke_prob = 1.0 / (1.0 + np.exp(-stroke_logit))
    stroke = (rng.random(n_users) < stroke_prob).astype(int)

    df = pd.DataFrame(
        {
            "id": ids,
            "gender": gender,
            "age": age,
            "hypertension": hypertension,
            "heart_disease": heart_disease,
            "ever_married": ever_married,
            "work_type": work_type,
            "Residence_type": residence_type,
            "avg_glucose_level": avg_glucose_level,
            "bmi": bmi,
            "smoking_status": smoking_status,
            "stroke": stroke,
        }
    )
    return df
