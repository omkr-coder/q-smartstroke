import React, { useCallback, useEffect, useState } from 'react'
import {
  ArrowUpRight,
  Atom,
  Award,
  Compass,
  FileSpreadsheet,
  Flame,
  ShieldAlert,
  Sparkles,
  Target,
} from 'lucide-react'
import { api } from './api'
import QQuestTab from './components/QQuestTab'
import RiskExplorerTab from './components/RiskExplorerTab'
import SafePathTab from './components/SafePathTab'
import ResearchExcelTab from './components/ResearchExcelTab'

const INITIAL_PROFILE = {
  gender: 'Female',
  age: 58,
  hypertension: 1,
  heart_disease: 0,
  ever_married: 'Yes',
  work_type: 'Private',
  Residence_type: 'Urban',
  avg_glucose_level: 162.4,
  bmi: 29.8,
  smoking_status: 'formerly smoked',
}

const SECTIONS = [
  { id: 'qquest', label: 'Q-Quest', title: 'Explore a fictional stroke-risk profile', action: 'Open Risk Explorer', next: 'explorer', icon: Target },
  { id: 'explorer', label: 'Risk Explorer', title: 'See how inputs change the model output', action: 'Try an uncertainty case', next: 'safepath', icon: Compass },
  { id: 'safepath', label: 'Q-SafePath', title: 'Practice interpreting uncertain predictions', action: 'Open Research Lab', next: 'excel', icon: ShieldAlert },
  { id: 'excel', label: 'Research Lab', title: 'Review model results and activity', action: 'Return to Q-Quest', next: 'qquest', icon: FileSpreadsheet },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('qquest')
  const [overview, setOverview] = useState(null)
  const [profile, setProfile] = useState(INITIAL_PROFILE)
  const [prediction, setPrediction] = useState(null)
  const [loadingPred, setLoadingPred] = useState(false)
  const [toast, setToast] = useState(null)
  const [overviewError, setOverviewError] = useState(null)
  const section = SECTIONS.find(({ id }) => id === activeTab)

  const showToast = useCallback((msg) => {
    setToast(msg)
    setTimeout(() => {
      setToast((prev) => (prev === msg ? null : prev))
    }, 3600)
  }, [])

  const loadOverview = useCallback(async () => {
    setOverviewError(null)
    const data = await api.getOverview()
    setOverview(data)
    return data
  }, [])

  const runPrediction = useCallback(
    async (prof, logToExcel = true) => {
      setLoadingPred(true)
      try {
        const res = await api.predict({ ...prof, log_to_excel: logToExcel })
        setPrediction(res.prediction)
        setOverview((prev) =>
          prev ? { ...prev, gamification: res.gamification, excel_sync: res.excel_sync } : prev
        )
      } catch (err) {
        showToast(`Prediction error: ${err.message}`)
      } finally {
        setLoadingPred(false)
      }
    },
    [showToast]
  )

  useEffect(() => {
    const key = 'q-smartstroke-session-logged'
    if (sessionStorage.getItem(key)) return
    sessionStorage.setItem(key, '1')
    api.trackActivity('qquest', 'session_start').catch(() => sessionStorage.removeItem(key))
  }, [])

  useEffect(() => {
    api.trackActivity(activeTab, 'screen_open').catch(console.error)
  }, [activeTab])

  useEffect(() => {
    loadOverview()
      .then(() => runPrediction(INITIAL_PROFILE, false))
      .catch((err) => setOverviewError(err.message))
  }, [loadOverview, runPrediction, showToast])

  // Poll background Excel auto-save status every 2.5 seconds
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const status = await api.getExcelStatus()
        setOverview((prev) => (prev ? { ...prev, excel_sync: status } : prev))
      } catch {
        // ignore transient poll errors
      }
    }, 2500)
    return () => clearInterval(timer)
  }, [])

  const handleCompleteMission = async (mission) => {
    try {
      const res = await api.recordEvent({
        module: 'Q-Quest',
        action_type: 'mission_completed',
        item_id: mission.id,
        outcome: 'correct',
        xp_earned: mission.xp,
        comprehension_score: 1.0,
        details: `${mission.title} (${mission.factor})`,
        mark_mission_id: mission.id,
      })
      setOverview((prev) => ({ ...prev, gamification: res.gamification, excel_sync: res.excel_sync }))
      showToast(`Mission completed! +${mission.xp} XP queued for Excel auto-save.`)
    } catch (err) {
      showToast(`Failed to record mission: ${err.message}`)
    }
  }

  const handleSolvePuzzle = async (puzzle) => {
    try {
      const res = await api.recordEvent({
        module: 'Risk Explorer',
        action_type: 'puzzle_solved',
        item_id: puzzle.id,
        outcome: 'verified',
        xp_earned: puzzle.xp,
        comprehension_score: 1.0,
        details: puzzle.title,
        mark_puzzle_id: puzzle.id,
      })
      setOverview((prev) => ({ ...prev, gamification: res.gamification, excel_sync: res.excel_sync }))
      showToast(`Puzzle solved! +${puzzle.xp} XP saved to Excel.`)
    } catch (err) {
      showToast(`Failed to record puzzle: ${err.message}`)
    }
  }

  const handleSafePathDecision = async (caseItem, actionId, isCorrect) => {
    try {
      const res = await api.recordEvent({
        module: 'Q-SafePath',
        action_type: 'clinical_decision',
        item_id: caseItem.case_id,
        outcome: isCorrect ? 'optimal' : 'suboptimal',
        xp_earned: isCorrect ? 65 : 15,
        comprehension_score: isCorrect ? 1.0 : 0.0,
        details: `Chosen=${actionId}, Recommended=${caseItem.recommended_action}`,
        safepath_is_correct: isCorrect,
      })
      setOverview((prev) => ({ ...prev, gamification: res.gamification, excel_sync: res.excel_sync }))
    } catch (err) {
      showToast(`Failed to record decision: ${err.message}`)
    }
  }

  const sync = overview?.excel_sync
  const gamification = overview?.gamification

  const syncClass =
    sync?.status === 'locked_retrying'
      ? 'locked'
      : sync?.dirty || sync?.status === 'pending_save'
        ? 'pending'
        : ''

  const syncLabel =
    !sync ? 'Connecting to Excel' : sync.status === 'locked_retrying'
      ? 'Excel Open (Retrying Save...)'
      : sync?.dirty
        ? `Auto-Saving (${sync.pending_changes})...`
        : `Excel Auto-Synced (${sync?.save_count ?? 0})`

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">
            <Atom size={24} />
          </div>
          <div>
            <h1>Q-SmartStroke</h1>
            <p>Stroke-risk literacy research workspace</p>
          </div>
        </div>

        <div className="hud-row">
          <div className="hud-pill">
            <Sparkles size={15} color="#0369a1" />
            <span>Lvl {gamification?.level ?? 1}</span>
            <span className="subtle">({gamification?.xp ?? 0} XP)</span>
          </div>
          <div className="hud-pill">
            <Flame size={15} color="#92400e" />
            <span>{gamification?.missions_completed ?? 0} Missions</span>
          </div>
          <div className="hud-pill">
            <Award size={15} color="#6d28d9" />
            <span>{gamification?.badges?.length ?? 0} Badges</span>
          </div>
          <button
            type="button"
            className={`hud-pill sync-pill ${syncClass}`}
            style={{ cursor: 'pointer' }}
            title={sync?.workbook_path || 'Click to open Excel tab'}
            onClick={() => setActiveTab('excel')}
          >
            <FileSpreadsheet size={15} />
            <span>{syncLabel}</span>
          </button>
        </div>
      </header>

      <nav className="nav-tabs" aria-label="Workspace">
        {SECTIONS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={`tab-btn ${activeTab === id ? 'active' : ''}`}
            aria-current={activeTab === id ? 'page' : undefined}
            onClick={() => setActiveTab(id)}
          >
            <Icon size={18} aria-hidden="true" />
            {label}
          </button>
        ))}
      </nav>

      <main id="workspace">
        <section className={`workspace-hero workspace-hero--${section.id}`} aria-labelledby="workspace-title">
          <div>
            <p className="workspace-label">{section.label}</p>
            <h2 id="workspace-title">{section.title}</h2>
          </div>
          <button className="btn hero-action" type="button" onClick={() => setActiveTab(section.next)}>
            {section.action} <ArrowUpRight size={17} aria-hidden="true" />
          </button>
        </section>
      {!overview ? (
        <section className="card startup-card" aria-live="polite">
          <Atom size={32} aria-hidden="true" />
          <h3>{overviewError ? 'Waiting for the backend' : 'Loading the research workspace'}</h3>
          {overviewError && (
            <>
              <p className="subtle">The model service may still be starting. Try connecting again in a moment.</p>
              <button className="btn btn-primary" type="button" onClick={() => {
                loadOverview()
                  .then(() => runPrediction(INITIAL_PROFILE, false))
                  .catch((err) => setOverviewError(err.message))
              }}>Retry connection</button>
            </>
          )}
        </section>
      ) : (
        <>
          {activeTab === 'qquest' && (
            <QQuestTab
              profile={profile}
              setProfile={setProfile}
              prediction={prediction}
              loadingPred={loadingPred}
              onRunPrediction={(prof) => runPrediction(prof, true)}
              gamification={gamification}
              onCompleteMission={handleCompleteMission}
            />
          )}

          {activeTab === 'explorer' && (
            <RiskExplorerTab
              globalInteractions={overview.global_interactions}
              puzzles={overview.puzzles}
              gamification={gamification}
              onSolvePuzzle={handleSolvePuzzle}
            />
          )}

          {activeTab === 'safepath' && (
            <SafePathTab
              cases={overview.safepath_cases}
              riskCoverageCurve={overview.risk_coverage_curve}
              gamification={gamification}
              onDecision={handleSafePathDecision}
            />
          )}

          {activeTab === 'excel' && (
            <ResearchExcelTab
              cohort={overview.cohort}
              benchmarks={overview.benchmarks}
              excelSync={sync}
              onSyncNow={async () => {
                const updated = await api.syncExcelNow()
                setOverview((prev) => ({ ...prev, excel_sync: updated }))
                showToast('Excel workbook saved atomically!')
              }}
              onToggleAutoSave={async (enabled) => {
                const updated = await api.toggleAutoSave(enabled)
                setOverview((prev) => ({ ...prev, excel_sync: updated }))
                showToast(`Background Excel auto-save ${enabled ? 'enabled' : 'paused'}.`)
              }}
              onRefreshOverview={loadOverview}
              showToast={showToast}
            />
          )}
        </>
      )}

      </main>

      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  )
}
