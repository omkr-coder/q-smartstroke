import React from 'react'

export default function QuantumCircuitViz({ qubitStates = [], contributions = [] }) {
  const width = 620
  const height = 228
  const startX = 95
  const rowGap = 32
  const topY = 26

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div className="subtle" style={{ marginBottom: 8 }}>
          6-Qubit ZZFeatureMap Quantum Encoding Circuit (2-Repetition Ring Entanglement)
        </div>
        <div style={{ overflowX: 'auto', background: '#ffffff', borderRadius: 12, border: '1px solid var(--border)', padding: 10 }}>
          <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', minWidth: 500, height: 'auto', display: 'block' }}>
            {qubitStates.map((q, idx) => {
              const y = topY + idx * rowGap
              const nextY = topY + ((idx + 1) % qubitStates.length) * rowGap
              const cx = 365 + (idx % 3) * 32
              return (
                <g key={q.qubit}>
                  {/* Qubit label */}
                  <text x={12} y={y + 4} fill="#475569" fontSize="11" fontWeight="600">
                    |{q.qubit}⟩ {q.label.slice(0, 10)}
                  </text>
                  {/* Wire */}
                  <line x1={startX} y1={y} x2={585} y2={y} stroke="rgba(148,163,184,0.35)" strokeWidth="1.5" />

                  {/* H gate */}
                  <rect x={112} y={y - 11} width={24} height={22} rx={5} fill="#0ea5e9" fillOpacity="0.22" stroke="#0369a1" />
                  <text x={124} y={y + 4} textAnchor="middle" fill="#075985" fontSize="11" fontWeight="700">
                    H
                  </text>

                  {/* Rz(2x) gate */}
                  <rect x={154} y={y - 11} width={66} height={22} rx={5} fill="#7c3aed" fillOpacity="0.24" stroke="#6d28d9" />
                  <text x={187} y={y + 4} textAnchor="middle" fill="#4c1d95" fontSize="10" fontWeight="600">
                    Rz({q.angle_rad.toFixed(2)})
                  </text>

                  {/* ZZ Entangler marker */}
                  {idx < qubitStates.length - 1 && (
                    <>
                      <line x1={250 + idx * 16} y1={y} x2={250 + idx * 16} y2={nextY} stroke="#047857" strokeWidth="1.6" />
                      <circle cx={250 + idx * 16} cy={y} r={4} fill="#047857" />
                      <circle cx={250 + idx * 16} cy={nextY} r={5} fill="#ffffff" stroke="#047857" strokeWidth="1.8" />
                    </>
                  )}

                  {/* Variational Ry/Rz ansatz block */}
                  <rect x={cx} y={y - 11} width={54} height={22} rx={5} fill="#f59e0b" fillOpacity="0.18" stroke="#92400e" />
                  <text x={cx + 27} y={y + 4} textAnchor="middle" fill="#78350f" fontSize="10" fontWeight="600">
                    U(θ{idx})
                  </text>

                  {/* Excitation bar at end of wire */}
                  <rect x={515} y={y - 7} width={60} height={14} rx={4} fill="rgba(148,163,184,0.14)" />
                  <rect
                    x={515}
                    y={y - 7}
                    width={Math.max(4, Math.round(q.prob_one * 60))}
                    height={14}
                    rx={4}
                    fill="#7dd3fc"
                  />
                  <text x={545} y={y + 3.5} textAnchor="middle" fill="#172033" fontSize="9.5" fontWeight="700">
                    {(q.prob_one * 100).toFixed(0)}% |1⟩
                  </text>
                </g>
              )
            })}
          </svg>
        </div>
      </div>

      {contributions.length > 0 && (
        <div>
          <div className="subtle" style={{ marginBottom: 8 }}>
            Local Quantum Kernel Attribution (QSVM Perturbation Impact)
          </div>
          <div style={{ display: 'grid', gap: 8 }}>
            {contributions.map((c) => {
              const positive = c.impact_pct >= 0
              const widthPct = Math.min(100, Math.max(6, Math.abs(c.impact_pct) * 3.2))
              return (
                <div key={c.feature} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 68px', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>{c.label}</span>
                  <div className="bar-track">
                    <div
                      className="bar-fill"
                      style={{
                        width: `${widthPct}%`,
                        background: positive ? 'linear-gradient(90deg, #f97316, #be123c)' : 'linear-gradient(90deg, #10b981, #0369a1)',
                      }}
                    />
                  </div>
                  <span
                    style={{
                      textAlign: 'right',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      color: positive ? '#9f1239' : '#047857',
                    }}
                  >
                    {positive ? '+' : ''}
                    {c.impact_pct}%
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
