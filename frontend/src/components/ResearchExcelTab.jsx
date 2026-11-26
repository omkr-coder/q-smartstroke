import React, { useEffect, useState } from 'react'
import { Database, Download, FileSpreadsheet, PlusCircle, RefreshCw, Search, Upload } from 'lucide-react'
import { api } from '../api'

const SHEETS = [
  'Users_Dataset',
  'Predictions_Log',
  'Gamification_Progress',
  'Interaction_Telemetry',
  'Model_Benchmarks',
]

export default function ResearchExcelTab({
  cohort,
  benchmarks = [],
  excelSync,
  onSyncNow,
  onToggleAutoSave,
  onRefreshOverview,
  showToast,
}) {
  const [activeSheet, setActiveSheet] = useState('Users_Dataset')
  const [sheetData, setSheetData] = useState({ columns: [], rows: [], total: 0, page: 1, page_size: 15 })
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [uploading, setUploading] = useState(false)
  const [adding, setAdding] = useState(false)

  const [newUser, setNewUser] = useState({
    gender: 'Male',
    age: 61,
    hypertension: 1,
    heart_disease: 0,
    ever_married: 'Yes',
    work_type: 'Private',
    Residence_type: 'Urban',
    avg_glucose_level: 168.5,
    bmi: 29.4,
    smoking_status: 'formerly smoked',
    stroke: 0,
  })

  const loadSheet = async (sheetName = activeSheet, p = page, q = search) => {
    try {
      const data = await api.getSheet(sheetName, p, 15, q)
      setSheetData(data)
    } catch (err) {
      showToast(`Failed to load sheet: ${err.message}`)
    }
  }

  useEffect(() => {
    loadSheet(activeSheet, page, search)
  }, [activeSheet, page, excelSync?.save_count])

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await api.uploadDataset(file)
      showToast(`Loaded ${res.rows_loaded} rows & retrained QSVM/VQC models! Saved to Excel.`)
      await onRefreshOverview()
      setPage(1)
      await loadSheet('Users_Dataset', 1, '')
    } catch (err) {
      showToast(`Upload error: ${err.message}`)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleAddUser = async (e) => {
    e.preventDefault()
    setAdding(true)
    try {
      const res = await api.addUserRow(newUser)
      showToast(`Added User #${res.added_user.id} (Hybrid Risk: ${res.prediction.hybrid_risk_pct}%) — queued for Excel auto-save!`)
      await onRefreshOverview()
      await loadSheet(activeSheet, 1, search)
    } catch (err) {
      showToast(`Failed to add user: ${err.message}`)
    } finally {
      setAdding(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Cohort & Benchmark Table */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">
            <Database size={18} color="#0369a1" />
            Quantum vs. Classical Benchmarking ({cohort?.total_users ?? 0} Users)
          </h2>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span className="badge badge-mod">Stroke+: {cohort?.stroke_positive ?? 0} ({cohort?.stroke_rate_pct ?? 0}%)</span>
            <span className="badge">Missing BMI: {cohort?.bmi_missing_count ?? 0}</span>
            <span className="badge">Unknown Smoking: {cohort?.unknown_smoking_count ?? 0}</span>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Family</th>
                <th>ROC-AUC</th>
                <th>PR-AUC (AUPRC)</th>
                <th>F1-Score</th>
                <th>Recall</th>
                <th>Precision</th>
                <th>Brier</th>
                <th>ECE</th>
              </tr>
            </thead>
            <tbody>
              {benchmarks.map((b) => (
                <tr key={b.model_name}>
                  <td style={{ fontWeight: 700 }}>{b.model_name}</td>
                  <td>
                    <span className={`badge ${b.family.includes('Quantum') ? 'badge-quantum' : ''}`}>{b.family}</span>
                  </td>
                  <td>{b.roc_auc}</td>
                  <td style={{ color: '#0369a1', fontWeight: 700 }}>{b.pr_auc}</td>
                  <td>{b.f1_score}</td>
                  <td>{b.recall}</td>
                  <td>{b.precision}</td>
                  <td>{b.brier_score}</td>
                  <td>{b.ece}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Live Background Excel Controls + Add User */}
      <div className="grid-equal-2">
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">
              <FileSpreadsheet size={18} color="#047857" />
              Background Excel Auto-Save Controls
            </h2>
            <span className="badge badge-low">Saves: {excelSync?.save_count ?? 0}</span>
          </div>

          <div className="subtle" style={{ lineHeight: 1.6, marginBottom: 12 }}>
            Workbook Path: <code>{excelSync?.workbook_path}</code>
            <br />
            Last Saved: <strong>{excelSync?.last_saved_at || 'Pending'}</strong> · Status:{' '}
            <strong>{excelSync?.status}</strong>
            {excelSync?.last_error && <div style={{ color: '#9f1239', marginTop: 4 }}>{excelSync.last_error}</div>}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 9 }}>
            <button type="button" className="btn btn-primary" onClick={onSyncNow}>
              <RefreshCw size={15} />
              Sync &amp; Save Now
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => onToggleAutoSave(!excelSync?.auto_save_enabled)}
            >
              Auto-Save: {excelSync?.auto_save_enabled ? 'ON (1.2s debounce)' : 'PAUSED'}
            </button>
            <a className="btn btn-emerald" href={api.downloadUrl} download="q_smartstroke_workbook.xlsx">
              <Download size={15} />
              Download .XLSX
            </a>
            <label className="btn" style={{ cursor: 'pointer' }}>
              <Upload size={15} />
              {uploading ? 'Importing & Retraining...' : 'Replace Dataset (CSV/XLSX)'}
              <input type="file" accept=".csv,.xlsx,.xls" hidden onChange={handleUpload} disabled={uploading} />
            </label>
          </div>
        </div>

        {/* Add New User directly to Excel sheet */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">
              <PlusCircle size={18} color="#6d28d9" />
              Append User Row to Excel &amp; Auto-Score
            </h2>
          </div>

          <form className="form-grid" onSubmit={handleAddUser}>
            <div className="field">
              <label>Age</label>
              <input
                type="number"
                value={newUser.age}
                onChange={(e) => setNewUser((p) => ({ ...p, age: Number(e.target.value) }))}
              />
            </div>
            <div className="field">
              <label>Avg Glucose</label>
              <input
                type="number"
                step="0.1"
                value={newUser.avg_glucose_level}
                onChange={(e) => setNewUser((p) => ({ ...p, avg_glucose_level: Number(e.target.value) }))}
              />
            </div>
            <div className="field">
              <label>BMI</label>
              <input
                type="number"
                step="0.1"
                value={newUser.bmi}
                onChange={(e) => setNewUser((p) => ({ ...p, bmi: Number(e.target.value) }))}
              />
            </div>
            <div className="field">
              <label>Hypertension</label>
              <select
                value={newUser.hypertension}
                onChange={(e) => setNewUser((p) => ({ ...p, hypertension: Number(e.target.value) }))}
              >
                <option value={0}>0 (No)</option>
                <option value={1}>1 (Yes)</option>
              </select>
            </div>
            <div className="field full">
              <button type="submit" className="btn btn-primary" disabled={adding}>
                <PlusCircle size={15} />
                {adding ? 'Adding & Queueing Save...' : 'Add Row to Users_Dataset & Predictions_Log'}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Live Multi-Sheet Excel Inspector */}
      <div className="card">
        <div className="card-header" style={{ flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
            {SHEETS.map((s) => (
              <button
                key={s}
                type="button"
                className={`tab-btn ${activeSheet === s ? 'active' : ''}`}
                style={{ padding: '7px 12px', fontSize: '0.8rem' }}
                onClick={() => {
                  setActiveSheet(s)
                  setPage(1)
                }}
              >
                {s} ({excelSync?.sheet_counts?.[s] ?? 0})
              </button>
            ))}
          </div>

          <form
            style={{ display: 'flex', gap: 6 }}
            onSubmit={(e) => {
              e.preventDefault()
              setPage(1)
              loadSheet(activeSheet, 1, search)
            }}
          >
            <input
              type="text"
              placeholder="Search sheet..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                background: 'var(--bg-elev)',
                border: '1px solid var(--border)',
                color: 'var(--text)',
                borderRadius: 8,
                padding: '7px 10px',
                fontSize: '0.82rem',
              }}
            />
            <button type="submit" className="btn">
              <Search size={14} />
            </button>
          </form>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {sheetData.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sheetData.rows.length === 0 ? (
                <tr>
                  <td colSpan={Math.max(sheetData.columns.length, 1)} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                    No rows yet in this sheet. Interact with Q-Quest or Q-SafePath to populate automatically!
                  </td>
                </tr>
              ) : (
                sheetData.rows.map((row, rIdx) => (
                  <tr key={rIdx}>
                    {sheetData.columns.map((col) => (
                      <td key={col}>{row[col] === null || row[col] === undefined ? '—' : String(row[col])}</td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
          <span className="subtle">
            Showing page {page} · {sheetData.total} matching rows
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <button
              type="button"
              className="btn"
              disabled={page * sheetData.page_size >= sheetData.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
