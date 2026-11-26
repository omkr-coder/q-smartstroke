import React, { useEffect, useState } from 'react'
import { CheckCircle2, Compass, Puzzle, Sparkles } from 'lucide-react'
import { api } from '../api'

const NODES = [
  { key: 'age', label: 'Age ≥ 60', x: 110, y: 80, desc: 'Chronological vascular aging' },
  { key: 'hypertension', label: 'Hypertension', x: 300, y: 55, desc: 'Elevated arterial pressure' },
  { key: 'heart_disease', label: 'Heart Disease', x: 485, y: 85, desc: 'Cardiac comorbidity' },
  { key: 'avg_glucose_level', label: 'High Glucose', x: 465, y: 220, desc: 'Hyperglycemia ≥ 180 mg/dL' },
  { key: 'bmi', label: 'Elevated BMI', x: 295, y: 245, desc: 'BMI ≥ 32 metabolic load' },
  { key: 'smoking_status', label: 'Active Smoking', x: 120, y: 215, desc: 'Vascular endothelial stress' },
]

export default function RiskExplorerTab({ globalInteractions = [], puzzles = [], gamification, onSolvePuzzle }) {
  const [activeNodes, setActiveNodes] = useState({
    age: false,
    hypertension: true,
    heart_disease: false,
    avg_glucose_level: false,
    bmi: false,
    smoking_status: false,
  })
  const [simResult, setSimResult] = useState(null)
  const [puzzleFeedback, setPuzzleFeedback] = useState({})

  const solvedIds = new Set(gamification?.solved_puzzle_ids || [])

  useEffect(() => {
    let cancelled = false
    const simProfile = {
      gender: 'Female',
      age: activeNodes.age ? 68 : 38,
      hypertension: activeNodes.hypertension ? 1 : 0,
      heart_disease: activeNodes.heart_disease ? 1 : 0,
      ever_married: 'Yes',
      work_type: 'Private',
      Residence_type: 'Urban',
      avg_glucose_level: activeNodes.avg_glucose_level ? 205 : 92,
      bmi: activeNodes.bmi ? 34.5 : 23.5,
      smoking_status: activeNodes.smoking_status ? 'smokes' : 'never smoked',
    }
    api
      .explore(simProfile)
      .then((res) => {
        if (!cancelled) setSimResult(res.prediction)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [activeNodes])

  const toggleNode = (key) => {
    setActiveNodes((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const checkPuzzle = async (puzzle) => {
    const selected = Object.entries(activeNodes)
      .filter(([, v]) => v)
      .map(([k]) => k)
    const target = puzzle.target_pair
    const match = target.every((t) => selected.includes(t)) && selected.length === target.length
    if (match) {
      setPuzzleFeedback((prev) => ({ ...prev, [puzzle.id]: `Discovery verified! +${puzzle.xp} XP saved to Excel.` }))
      await onSolvePuzzle(puzzle)
    } else {
      setPuzzleFeedback((prev) => ({
        ...prev,
        [puzzle.id]: `Currently selected ${selected.length} node(s). Hint: ${puzzle.hint}`,
      }))
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="grid-equal-2">
        {/* Interactive Quantum Constellation */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">
              <Compass size={18} color="#0369a1" />
              Quantum Risk-Factor Constellation (ZZFeatureMap)
            </h2>
            <span className="badge badge-quantum">Interactive Sandbox</span>
          </div>
          <p className="subtle" style={{ marginTop: 0 }}>
            Click risk nodes below to activate/deactivate factors and observe live Quantum Kernel risk synergy.
          </p>

          <div style={{ background: '#ffffff', borderRadius: 12, border: '1px solid var(--border)', padding: 8, marginBottom: 12 }}>
            <svg viewBox="0 0 600 300" style={{ width: '100%', height: 'auto', display: 'block' }}>
              {/* Entanglement edges */}
              {NODES.map((a, i) =>
                NODES.slice(i + 1).map((b) => {
                  const bothOn = activeNodes[a.key] && activeNodes[b.key]
                  return (
                    <line
                      key={`${a.key}-${b.key}`}
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      stroke={bothOn ? '#6d28d9' : 'rgba(148,163,184,0.16)'}
                      strokeWidth={bothOn ? 2.6 : 1}
                      strokeDasharray={bothOn ? undefined : '4 4'}
                    />
                  )
                })
              )}

              {/* Nodes */}
              {NODES.map((n) => {
                const on = activeNodes[n.key]
                return (
                  <g key={n.key} onClick={() => toggleNode(n.key)} style={{ cursor: 'pointer' }}>
                    <circle
                      cx={n.x}
                      cy={n.y}
                      r={on ? 32 : 26}
                      fill={on ? 'rgba(56,189,248,0.22)' : '#f1f5f9'}
                      stroke={on ? '#0369a1' : 'rgba(148,163,184,0.4)'}
                      strokeWidth={on ? 2.5 : 1.5}
                    />
                    <text x={n.x} y={n.y + 4} textAnchor="middle" fill={on ? '#075985' : '#475569'} fontSize="10.5" fontWeight="700">
                      {n.label}
                    </text>
                  </g>
                )
              })}
            </svg>
          </div>

          <div className="grid-3">
            {NODES.map((n) => (
              <button
                key={n.key}
                type="button"
                className={`node-btn ${activeNodes[n.key] ? 'active' : ''}`}
                onClick={() => toggleNode(n.key)}
              >
                <div style={{ fontWeight: 700, fontSize: '0.84rem' }}>{n.label}</div>
                <div className="subtle" style={{ fontSize: '0.73rem' }}>
                  {n.desc}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Live Simulation Output + Cohort Interaction Evidence */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">
              <Sparkles size={18} color="#6d28d9" />
              Live Quantum Interaction Response
            </h2>
            {simResult && <span className="badge">{simResult.top_interaction}</span>}
          </div>

          {simResult && (
            <div className="grid-3" style={{ marginBottom: 16 }}>
              <div className="stat-box">
                <div className="stat-label">Hybrid Quantum Risk</div>
                <div className="stat-value" style={{ color: '#0369a1' }}>
                  {simResult.hybrid_risk_pct}%
                </div>
              </div>
              <div className="stat-box">
                <div className="stat-label">QSVM Score</div>
                <div className="stat-value" style={{ color: '#6d28d9' }}>
                  {simResult.qsvm_risk_pct}%
                </div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Uncertainty</div>
                <div className="stat-value" style={{ color: '#92400e' }}>
                  {simResult.uncertainty_pct}%
                </div>
              </div>
            </div>
          )}

          <div className="subtle" style={{ marginBottom: 8 }}>
            Discovered Pairwise Interactions Across the 5,000-User Dataset
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Interaction Pair</th>
                  <th>Cohort n</th>
                  <th>Combined Rate</th>
                  <th>Amplification</th>
                </tr>
              </thead>
              <tbody>
                {globalInteractions.map((g) => (
                  <tr key={g.id}>
                    <td style={{ fontWeight: 600 }}>{g.label}</td>
                    <td>{g.cohort_count}</td>
                    <td>{g.both_stroke_rate_pct}%</td>
                    <td>
                      <span className="badge badge-high">{g.amplification_x}×</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Discovery Puzzle Levels */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">
            <Puzzle size={18} color="#047857" />
            Risk-Factor Discovery Puzzles
          </h2>
          <span className="subtle">Toggle ONLY the matching pair in the constellation above, then verify</span>
        </div>

        <div className="grid-3">
          {puzzles.map((p) => {
            const solved = solvedIds.has(p.id)
            return (
              <div key={p.id} className={`mission-card ${solved ? 'done' : ''}`}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="badge badge-quantum">Level {p.level}</span>
                  <span className="badge">+{p.xp} XP</span>
                </div>
                <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {solved && <CheckCircle2 size={16} color="#047857" />}
                  {p.title}
                </div>
                <div className="subtle">{p.prompt}</div>
                {puzzleFeedback[p.id] && (
                  <div style={{ fontSize: '0.8rem', color: solved ? '#047857' : '#854d0e' }}>{puzzleFeedback[p.id]}</div>
                )}
                <button type="button" className="btn btn-emerald" disabled={solved} onClick={() => checkPuzzle(p)}>
                  {solved ? 'Solved & Saved' : 'Verify Constellation Pair'}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
