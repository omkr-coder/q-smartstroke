const API_BASE = ''
const sessionKey = 'q-smartstroke-session'
function createSessionId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-')
}
const sessionId = sessionStorage.getItem(sessionKey) || createSessionId()
sessionStorage.setItem(sessionKey, sessionId)

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers: { ...options.headers, "X-Session-ID": sessionId } })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      // ignore non-json error body
    }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  trackActivity: (section, action) => request(
    '/api/activity?' + new URLSearchParams({ section, action }),
    { method: 'POST' },
  ),

  getOverview: () => request('/api/overview'),
  predict: (profile) =>
    request('/api/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    }),
  explore: (profile) =>
    request('/api/explore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...profile, log_to_excel: false }),
    }),
  recordEvent: (eventPayload) =>
    request('/api/gamification/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(eventPayload),
    }),
  getExcelStatus: () => request('/api/excel/status'),
  syncExcelNow: () => request('/api/excel/sync-now', { method: 'POST' }),
  toggleAutoSave: (enabled) =>
    request('/api/excel/auto-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    }),
  getSheet: (sheetName, page = 1, pageSize = 20, search = '') =>
    request(
      `/api/excel/sheet/${encodeURIComponent(sheetName)}?page=${page}&page_size=${pageSize}&search=${encodeURIComponent(search)}`
    ),
  addUserRow: (userRow) =>
    request('/api/excel/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(userRow),
    }),
  uploadDataset: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/api/excel/upload', {
      method: 'POST',
      body: fd,
    })
  },
  downloadUrl: '/api/excel/download',
}
