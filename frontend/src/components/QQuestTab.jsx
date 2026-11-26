import React, { useState } from 'react'
import { Activity, CheckCircle2, Cpu, Sparkles, Target, UserCheck } from 'lucide-react'
import QuantumCircuitViz from './QuantumCircuitViz'

const PRESET_PROFILES = [
  {
    label: 'High-Risk Senior (Hypertension + Glucose)',
    profile: {
      gender: 'Male',
      age: 69,
      hypertension: 1,
      heart_disease: 1,
      ever_married: 'Yes',
      work_type: 'Self-employed',
      Residence_type: 'Urban',
      avg_glucose_level: 214.5,
      bmi: 31.4,
      smoking_status: 'formerly smoked',
    },
  },
  {
    label: 'Borderline / Uncertain Profile',
    profile: {
      gender: 'Female',
      age: 56,
      hypertension: 1,
      heart_disease: 0,
      ever_married: 'Yes',
      work_type: 'Private',
      Residence_type: 'Rural',
      avg_glucose_level: 146.2,
      bmi: null,
      smoking_status: 'Unknown',
    },
  },
  {
    label: 'Low-Risk Preventive Profile',
    profile: {
      gender: 'Female',
      age: 31,
      hypertension: 0,
      heart_disease: 0,
      ever_married: 'No',
      work_type: 'Private',
      Residence_type: 'Urban',
      avg_glucose_level: 88.4,
      bmi: 22.8,
      smoking_status: 'never smoked',
    },
  },
]

export default function QQuestTab({
  profile,
  setProfile,
  prediction,
  loadingPred,
  onRunPrediction,
  gamification,
  onCompleteMission,
}) {
  const [selectedAnswers, setSelectedAnswers] = useState({})
  const [quizFeedback, setQuizFeedback] = useState({})

  const completedIds = new Set(gamification?.completed_mission_ids || [])

  const updateField = (key, value) => {
    setProfile((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmitMission = async (mission) => {
    const chosen = selectedAnswers[mission.id]
    if (chosen === undefined) return
    const isCorrect = chosen === mission.correct_index
    setQuizFeedback((prev) => ({
      ...prev,
      [mission.id]: isCorrect
        ? `Correct! +${mission.xp} XP saved to Excel.`
        : 'Not quite — review the explanation and try again!',
    }))
    if (isCorrect) {
      await onCompleteMission(mission)
    }
  }

  const riskBadgeClass =
    prediction?.risk_category === 'High Risk'
      ? 'badge-high'
      : prediction?.risk_category === 'Moderate Risk'
        ? 'badge-mod'
        : 'badge-low'

  return (
    <div className="grid-2">
      {/* Left: User Health Profile Input */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">
            <UserCheck size={18} color="#0369a1" />
            Health Profile (12-Col Schema)
          </h2>
          <span className="badge badge-quantum">6 Qubits</span>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
          {PRESET_PROFILES.map((p) => (
            <button
              key={p.label}
              type="button"
              className="btn"
              style={{ fontSize: '0.74rem', padding: '5px 9px' }}
              onClick={() => {
                setProfile(p.profile)
                onRunPrediction(p.profile)
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault()
            onRunPrediction(profile)
          }}
        >
          <div className="field">
            <label>Age (years)</label>
            <input
              type="number"
              min="1"
              max="100"
              step="1"
              value={profile.age}
              onChange={(e) => updateField('age', Number(e.target.value))}
            />
          </div>

          <div className="field">
            <label>Gender</label>
            <select value={profile.gender} onChange={(e) => updateField('gender', e.target.value)}>
              <option value="Female">Female</option>
              <option value="Male">Male</option>
              <option value="Other">Other</option>
            </select>
          </div>

          <div className="field">
            <label>Hypertension</label>
            <select value={profile.hypertension} onChange={(e) => updateField('hypertension', Number(e.target.value))}>
              <option value={0}>No (0)</option>
              <option value={1}>Yes (1)</option>
            </select>
          </div>

          <div className="field">
            <label>Heart Disease</label>
            <select value={profile.heart_disease} onChange={(e) => updateField('heart_disease', Number(e.target.value))}>
              <option value={0}>No (0)</option>
              <option value={1}>Yes (1)</option>
            </select>
          </div>

          <div className="field">
            <label>Avg Glucose Level (mg/dL)</label>
            <input
              type="number"
              min="40"
              max="350"
              step="0.1"
              value={profile.avg_glucose_level}
              onChange={(e) => updateField('avg_glucose_level', Number(e.target.value))}
            />
          </div>

          <div className="field">
            <label>BMI (blank = missing/imputed)</label>
            <input
              type="number"
              min="10"
              max="70"
              step="0.1"
              placeholder="Missing (auto-impute)"
              value={profile.bmi ?? ''}
              onChange={(e) => updateField('bmi', e.target.value === '' ? null : Number(e.target.value))}
            />
          </div>

          <div className="field">
            <label>Smoking Status</label>
            <select value={profile.smoking_status} onChange={(e) => updateField('smoking_status', e.target.value)}>
              <option value="never smoked">never smoked</option>
              <option value="formerly smoked">formerly smoked</option>
              <option value="smokes">smokes</option>
              <option value="Unknown">Unknown</option>
            </select>
          </div>

          <div className="field">
            <label>Ever Married</label>
            <select value={profile.ever_married} onChange={(e) => updateField('ever_married', e.target.value)}>
              <option value="Yes">Yes</option>
              <option value="No">No</option>
            </select>
          </div>

          <div className="field">
            <label>Work Type</label>
            <select value={profile.work_type} onChange={(e) => updateField('work_type', e.target.value)}>
              <option value="Private">Private</option>
              <option value="Self-employed">Self-employed</option>
              <option value="Govt_job">Govt_job</option>
              <option value="children">children</option>
              <option value="Never_worked">Never_worked</option>
            </select>
          </div>

          <div className="field">
            <label>Residence Type</label>
            <select value={profile.Residence_type} onChange={(e) => updateField('Residence_type', e.target.value)}>
              <option value="Urban">Urban</option>
              <option value="Rural">Rural</option>
            </select>
          </div>

          <div className="field full" style={{ marginTop: 6 }}>
            <button type="submit" className="btn btn-primary" disabled={loadingPred}>
              <Cpu size={16} />
              {loadingPred ? 'Running Quantum Circuit...' : 'Predict Risk & Auto-Log to Excel'}
            </button>
          </div>
        </form>
      </div>

      {/* Right: Hybrid Quantum Prediction + Adaptive Missions */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        {prediction && (
          <>
            <div className="card">
              <div className="card-header">
                <h2 className="card-title">
                  <Activity size={18} color="#6d28d9" />
                  Hybrid Quantum-Classical Stroke Assessment
                </h2>
                <span className={`badge ${riskBadgeClass}`}>{prediction.risk_category}</span>
              </div>

              <div className="grid-4" style={{ marginBottom: 14 }}>
                <div className="stat-box">
                  <div className="stat-label">Hybrid Risk Score</div>
                  <div className="stat-value" style={{ color: '#0369a1' }}>
                    {prediction.hybrid_risk_pct}%
                  </div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">QSVM (ZZ Kernel)</div>
                  <div className="stat-value" style={{ color: '#6d28d9' }}>
                    {prediction.qsvm_risk_pct}%
                  </div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">VQC (Ansatz)</div>
                  <div className="stat-value" style={{ color: '#4338ca' }}>
                    {prediction.vqc_risk_pct}%
                  </div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">Epistemic Uncertainty</div>
                  <div className="stat-value" style={{ color: '#92400e' }}>
                    {prediction.uncertainty_pct}%
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 10,
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 13px',
                  borderRadius: 11,
                  background: 'var(--bg-elev)',
                  border: '1px solid var(--border)',
                  marginBottom: 16,
                }}
              >
                <div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700 }}>{prediction.confidence_tier}</div>
                  <div className="subtle">{prediction.clinical_rationale}</div>
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <span className="badge badge-quantum">Conformal Set: {`{${prediction.conformal_set.join(', ')}}`}</span>
                  <span className="badge">{prediction.top_interaction}</span>
                </div>
              </div>

              <QuantumCircuitViz
                qubitStates={prediction.qubit_states}
                contributions={prediction.feature_contributions}
              />
            </div>

            {/* Adaptive Q-Quest Missions */}
            <div className="card">
              <div className="card-header">
                <h2 className="card-title">
                  <Target size={18} color="#047857" />
                  Q-Quest: Personalized Prevention Missions
                </h2>
                <span className="subtle">Auto-generated from risk drivers · Progress saves to Excel</span>
              </div>

              <div style={{ display: 'grid', gap: 12 }}>
                {prediction.missions.map((m) => {
                  const isDone = completedIds.has(m.id)
                  return (
                    <div key={m.id} className={`mission-card ${isDone ? 'done' : ''}`}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {isDone ? <CheckCircle2 size={18} color="#047857" /> : <Sparkles size={17} color="#92400e" />}
                          <strong>{m.title}</strong>
                          <span className="badge">{m.factor}</span>
                        </div>
                        <span className="badge badge-quantum">+{m.xp} XP</span>
                      </div>

                      <div className="subtle">{m.description}</div>

                      <div style={{ fontSize: '0.84rem', fontWeight: 600, marginTop: 2 }}>{m.quiz_prompt}</div>
                      <div style={{ display: 'grid', gap: 6 }}>
                        {m.quiz_options.map((opt, idx) => (
                          <button
                            key={opt}
                            type="button"
                            className={`quiz-opt ${selectedAnswers[m.id] === idx ? 'selected' : ''}`}
                            disabled={isDone}
                            onClick={() => setSelectedAnswers((prev) => ({ ...prev, [m.id]: idx }))}
                          >
                            {opt}
                          </button>
                        ))}
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                        <span className="subtle" style={{ color: isDone ? '#047857' : '#854d0e' }}>
                          {isDone ? 'Completed & logged to Excel' : quizFeedback[m.id] || `Difficulty: ${m.difficulty}`}
                        </span>
                        {!isDone && (
                          <button
                            type="button"
                            className="btn btn-emerald"
                            disabled={selectedAnswers[m.id] === undefined}
                            onClick={() => handleSubmitMission(m)}
                          >
                            Complete Mission
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
