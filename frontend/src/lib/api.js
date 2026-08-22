const BASE = window.location.origin

export async function fetchValidation() {
  const r = await fetch(`${BASE}/api/validation`)
  if (!r.ok) throw new Error('validation fetch failed')
  return r.json()
}

export async function fetchOverlay(speedKmh = 300) {
  const r = await fetch(`${BASE}/api/overlay?speed_kmh=${speedKmh}`)
  if (!r.ok) throw new Error('overlay fetch failed')
  return r.json()
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
