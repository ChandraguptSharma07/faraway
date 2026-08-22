const BASE = window.location.origin

export async function fetchValidation() {
  const r = await fetch(`${BASE}/api/validation`)
  if (!r.ok) throw new Error('validation fetch failed')
  return r.json()
}

export async function fetchCalibrationStatus() {
  const r = await fetch(`${BASE}/api/calibration-status`)
  if (!r.ok) throw new Error('calibration status fetch failed')
  return r.json()
}

export async function fetchOverlay(speedKmh = 300) {
  const r = await fetch(`${BASE}/api/overlay?speed_kmh=${speedKmh}`)
  if (!r.ok) throw new Error('overlay fetch failed')
  return r.json()
}

export async function fetchShadowValidation() {
  const r = await fetch(`${BASE}/api/shadow-validation`)
  if (!r.ok) throw new Error('shadow validation fetch failed')
  return r.json()
}

export async function fetchModalCalibration() {
  const r = await fetch(`${BASE}/api/modal-calibration`)
  if (!r.ok) throw new Error('modal calibration fetch failed')
  return r.json()
}

export async function fetchJourneys(includeArchived = false) {
  const r = await fetch(`${BASE}/api/journeys?include_archived=${includeArchived}`)
  if (!r.ok) throw new Error('journey catalogue fetch failed')
  return r.json()
}

export async function fetchJourneyRecords(id, options = {}) {
  const params = new URLSearchParams({
    source: options.source ?? 'events',
    cursor: String(options.cursor ?? 0),
    limit: String(options.limit ?? 25),
  })
  if (options.stream) params.set('stream', options.stream)
  const r = await fetch(`${BASE}/api/journeys/${id}/records?${params}`)
  if (!r.ok) throw new Error('journey record fetch failed')
  return r.json()
}

export async function updateJourneyMetadata(id, metadata) {
  const r = await fetch(`${BASE}/api/journeys/${id}/metadata`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(metadata),
  })
  if (!r.ok) throw new Error('journey metadata update failed')
  return r.json()
}

export async function archiveJourney(id) {
  const r = await fetch(`${BASE}/api/journeys/${id}/archive`, { method: 'POST' })
  if (!r.ok) throw new Error('journey archive failed')
  return r.json()
}

export async function deleteJourney(id, confirmation) {
  const r = await fetch(`${BASE}/api/journeys/${id}?confirm=${encodeURIComponent(confirmation)}`, {
    method: 'DELETE',
  })
  if (!r.ok) throw new Error('journey deletion failed')
}

export function journeyExportUrl(id, format) {
  return `${BASE}/api/journeys/${id}/export?format=${format}`
}

const METRIC_LABELS = {
  mean_N: 'Mean force Fm',
  std_N: 'Std deviation',
  stat_max_N: 'Statistical max',
  stat_min_N: 'Statistical min',
  max_uplift_mm: 'Max uplift',
  loss_of_contact_pct: 'Loss of contact',
}
const METRIC_UNITS = {
  mean_N: 'N', std_N: 'N', stat_max_N: 'N', stat_min_N: 'N',
  max_uplift_mm: 'mm', loss_of_contact_pct: '%',
}
export { METRIC_LABELS, METRIC_UNITS }
