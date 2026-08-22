const BASE = window.location.origin

/**
 * Fetches validation data from the API.
 *
 * @returns {Promise<any>} The validation data.
 * @throws {Error} If the fetch request fails.
 */
export async function fetchValidation() {
  const r = await fetch(`${BASE}/api/validation`)
  if (!r.ok) throw new Error('validation fetch failed')
  return r.json()
}

/**
 * Fetches the calibration status from the API.
 *
 * @returns {Promise<any>} The calibration status data.
 * @throws {Error} If the fetch request fails.
 */
export async function fetchCalibrationStatus() {
  const r = await fetch(`${BASE}/api/calibration-status`)
  if (!r.ok) throw new Error('calibration status fetch failed')
  return r.json()
}

/**
 * Fetches overlay data for a given speed.
 *
 * @param {number} [speedKmh=300] - The speed in kilometers per hour.
 * @returns {Promise<any>} The overlay data.
 * @throws {Error} If the fetch request fails.
 */
export async function fetchOverlay(speedKmh = 300) {
  const r = await fetch(`${BASE}/api/overlay?speed_kmh=${speedKmh}`)
  if (!r.ok) throw new Error('overlay fetch failed')
  return r.json()
}

/**
 * Fetches shadow validation data from the API.
 *
 * @returns {Promise<any>} The shadow validation data.
 * @throws {Error} If the fetch request fails.
 */
export async function fetchShadowValidation() {
  const r = await fetch(`${BASE}/api/shadow-validation`)
  if (!r.ok) throw new Error('shadow validation fetch failed')
  return r.json()
}

/**
 * Fetches modal calibration data from the API.
 *
 * @returns {Promise<any>} The modal calibration data.
 * @throws {Error} If the fetch request fails.
 */
export async function fetchModalCalibration() {
  const r = await fetch(`${BASE}/api/modal-calibration`)
  if (!r.ok) throw new Error('modal calibration fetch failed')
  return r.json()
}

/**
 * Fetches a list of journeys, optionally including archived ones.
 *
 * @param {boolean} [includeArchived=false] - Whether to include archived journeys.
 * @returns {Promise<any>} The list of journeys.
 * @throws {Error} If the fetch request fails.
 */
export async function fetchJourneys(includeArchived = false) {
  const r = await fetch(`${BASE}/api/journeys?include_archived=${includeArchived}`)
  if (!r.ok) throw new Error('journey catalogue fetch failed')
  return r.json()
}

/**
 * Fetches records for a specific journey with pagination and filtering options.
 *
 * @param {string|number} id - The ID of the journey.
 * @param {Object} [options={}] - Options for fetching records.
 * @param {string} [options.source='events'] - The source of the records.
 * @param {number|string} [options.cursor=0] - The cursor for pagination.
 * @param {number|string} [options.limit=25] - The maximum number of records to fetch.
 * @param {string} [options.stream] - An optional stream identifier.
 * @returns {Promise<any>} The journey records.
 * @throws {Error} If the fetch request fails.
 */
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

/**
 * Updates the metadata for a specific journey.
 *
 * @param {string|number} id - The ID of the journey to update.
 * @param {Object} metadata - The new metadata to apply.
 * @returns {Promise<any>} The updated journey metadata.
 * @throws {Error} If the update request fails.
 */
export async function updateJourneyMetadata(id, metadata) {
  const r = await fetch(`${BASE}/api/journeys/${id}/metadata`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(metadata),
  })
  if (!r.ok) throw new Error('journey metadata update failed')
  return r.json()
}

/**
 * Archives a specific journey.
 *
 * @param {string|number} id - The ID of the journey to archive.
 * @returns {Promise<any>} The result of the archive operation.
 * @throws {Error} If the archive request fails.
 */
export async function archiveJourney(id) {
  const r = await fetch(`${BASE}/api/journeys/${id}/archive`, { method: 'POST' })
  if (!r.ok) throw new Error('journey archive failed')
  return r.json()
}

/**
 * Deletes a specific journey. Requires a confirmation string.
 *
 * @param {string|number} id - The ID of the journey to delete.
 * @param {string} confirmation - The confirmation string required to authorize deletion.
 * @returns {Promise<void>} Resolves when the journey is deleted.
 * @throws {Error} If the deletion request fails.
 */
export async function deleteJourney(id, confirmation) {
  const r = await fetch(`${BASE}/api/journeys/${id}?confirm=${encodeURIComponent(confirmation)}`, {
    method: 'DELETE',
  })
  if (!r.ok) throw new Error('journey deletion failed')
}

/**
 * Generates an export URL for a specific journey and format.
 *
 * @param {string|number} id - The ID of the journey to export.
 * @param {string} format - The export format (e.g., 'csv', 'json').
 * @returns {string} The fully qualified export URL.
 */
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
