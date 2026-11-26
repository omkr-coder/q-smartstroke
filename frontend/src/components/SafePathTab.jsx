import React, { useState } from 'react'
import { AlertTriangle, CheckCircle2, ShieldAlert } from 'lucide-react'

const ACTIONS = [
  {
    id: 'routine_prevention',
    title: 'Routine Lifestyle Prevention',
    subtitle: 'Low risk + tight conformal confidence',
  },
  {
    id: 'targeted_monitoring',
    title: 'Targeted Follow-Up & Monitoring',
    subtitle: 'Moderate risk or elevated epistemic uncertainty',
  },
  {
    id: 'urgent_clinical_review',
    title: 'Urgent Clinical Screening',
    subtitle: 'High risk or indeterminate {Low, High} conformal set',
  },
]

export default function SafePathTab({ cases = [], riskCoverageCurve = [], gamification, onDecision }) {
  const [idx, setIdx] = useState(0)
  const [feedback, setFeedback] = useState(null)

  if (!cases.length) {
    return <div className="card">Loading Q-SafePath conformal cases...</div>
  }

  const current = cases[idx % cases.length]
  const accuracy =
    gamification?.safepath_cases > 0
      ? Math.round((gamification.safepath_correct / gamification.safepath_cases) * 100)
      : 100

  const handleChoose = async (actionId) => {
    const isCorrect = actionId === current.recommended_action
    setFeedback({
      isCorrect,
      message: isCorrect
        ? `Optimal uncertainty-aware decision! ${current.rationale}`
        : `Suboptimal choice. Recommended: ${ACTIONS.find((a) => a.id === current.recommended_action)?.title}. ${current.rationale}`,
    })
    await onDecision(current, actionId, isCorrect)
  }

  return (
    <div className="grid-equal-2">
      {/* Patient Decision Challenge */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">
            <ShieldAlert size={18} color="#92400e" />
            Q-SafePath: Uncertainty-Aware Decision Challenge
          </h2>
          <span className="badge badge-quantum">
            Case {(idx % cases.length) + 1} / {cases.length}
          </span>
        </div>

        <div className="grid-3" style={{ marginBottom: 14 }}>
          <div className="stat-box">
            <div className="stat-label">Hybrid Quantum Risk</div>
            <div className="stat-value" style={{ color: '#0369a1' }}>
              {current.prediction.hybrid_risk_pct}%
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Epistemic Uncertainty</div>
            <div className="stat-value" style={{ color: '#92400e' }}>
              {current.prediction.uncertainty_pct}%
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Decision Accuracy</div>
            <div className="stat-value" style={{ color: '#047857' }}>
              {accuracy}%
            </div>
          </div>
        </div>

        <div
          style={{
            padding: 13,
            borderRadius: 12,
            background: 'var(--bg-elev)',
            border: '1px solid var(--border)',
            marginBottom: 14,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
            <strong>Simulated Patient #{current.user_id}</strong>
            <span className="badge badge-mod">
              Conformal Set: {`{${current.prediction.conformal_set.join(', ')}}`}
            </span>
          </div>
          <div className="subtle" style={{ lineHeight: 1.65 }}>
            Age: <strong>{current.profile.age}</strong> · Gender: <strong>{current.profile.gender}</strong> ·
            Hypertension: <strong>{current.profile.hypertension ? 'Yes' : 'No'}</strong> · Heart Disease:{' '}
            <strong>{current.profile.heart_disease ? 'Yes' : 'No'}</strong>
            <br />
            Avg Glucose: <strong>{current.profile.avg_glucose_level} mg/dL</strong> · BMI:{' '}
            <strong>{current.profile.bmi ?? 'Missing (Imputed)'}</strong> · Smoking:{' '}
            <strong>{current.profile.smoking_status}</strong>
          </div>
          <div style={{ marginTop: 8, fontSize: '0.82rem', color: '#854d0e' }}>
            Confidence Tier: {current.prediction.confidence_tier}
          </div>
        </div>

        <div style={{ display: 'grid', gap: 9, marginBottom: 14 }}>
          {ACTIONS.map((a) => (
            <button
              key={a.id}
              type="button"
              className="node-btn"
              onClick={() => handleChoose(a.id)}
            >
              <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>{a.title}</div>
              <div className="subtle" style={{ fontSize: '0.78rem' }}>
                {a.subtitle}
              </div>
            </button>
          ))}
        </div>

        {feedback && (
          <div
            style={{
              padding: 12,
              borderRadius: 10,
              border: `1px solid ${feedback.isCorrect ? 'rgba(52,211,153,0.45)' : 'rgba(251,113,133,0.45)'}`,
              background: feedback.isCorrect ? 'rgba(16,185,129,0.1)' : 'rgba(244,63,94,0.1)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 9,
              marginBottom: 12,
            }}
          >
            {feedback.isCorrect ? <CheckCircle2 size={18} color="#047857" /> : <AlertTriangle size={18} color="#be123c" />}
            <span style={{ fontSize: '0.83rem' }}>{feedback.message}</span>
          </div>
        )}

        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            setFeedback(null)
            setIdx((prev) => prev + 1)
          }}
        >
          Next Simulated Case →
        </button>
      </div>

      {/* Risk-Coverage Calibration & Conformal Explanation */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Conformal Risk-Coverage Calibration</h2>
          <span className="badge">Target Coverage: 88% (α = 0.12)</span>
        </div>
        <p className="subtle" style={{ marginTop: 0 }}>
          When high-uncertainty cases are deferred to clinical review instead of forced into binary predictions, decision
          accuracy on covered predictions increases cleanly.
        </p>

        <div style={{ display: 'grid', gap: 11, marginTop: 14 }}>
          {riskCoverageCurve.map((pt) => (
            <div key={pt.coverage} style={{ display: 'grid', gridTemplateColumns: '125px 1fr 64px', gap: 10, alignItems: 'center' }}>
              <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>Coverage {pt.coverage}%</span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{
                    width: `${pt.accuracy}%`,
                    background: 'linear-gradient(90deg, #0369a1, #047857)',
                  }}
                />
              </div>
              <span style={{ textAlign: 'right', fontWeight: 700, fontSize: '0.82rem', color: '#047857' }}>
                {pt.accuracy}%
              </span>
            </div>
          ))}
        </div>

        <div
          style={{
            marginTop: 18,
            padding: 13,
            borderRadius: 11,
            background: 'var(--bg-elev)',
            border: '1px solid var(--border)',
          }}
        >
          <strong style={{ fontSize: '0.86rem' }}>Research Literacy Takeaways</strong>
          <ul className="subtle" style={{ margin: '8px 0 0', paddingLeft: 18, lineHeight: 1.65 }}>
            <li>Conformal sets output both labels <code>{`{Low Risk, High Risk}`}</code> when nonconformity exceeds calibration quantile.</li>
            <li>Missing BMI or Unknown smoking status raises epistemic uncertainty—never treat missing data as zero risk.</li>
            <li>All case answers and comprehension outcomes are logged automatically to Excel <code>Interaction_Telemetry</code>.</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
