import { useEffect, useMemo, useRef, useState } from 'react'
import {
  archiveJourney,
  deleteJourney,
  fetchJourneys,
  fetchJourneyRecords,
  journeyExportUrl,
  updateJourneyMetadata,
} from '../lib/api'
import './JourneyLogs.css'

const FIELDS = [
  ['train_name', 'Train name', 'text'],
  ['train_id', 'Train identifier', 'text'],
  ['route_name', 'Route name', 'text'],
  ['route_id', 'Route identifier', 'text'],
  ['origin', 'Origin', 'text'],
  ['destination', 'Destination', 'text'],
  ['direction', 'Direction', 'text'],
  ['track', 'Track', 'text'],
  ['start_chainage_km', 'Start chainage (km)', 'number'],
  ['end_chainage_km', 'End chainage (km)', 'number'],
  ['start_latitude', 'Start latitude', 'number'],
  ['start_longitude', 'Start longitude', 'number'],
  ['end_latitude', 'End latitude', 'number'],
  ['end_longitude', 'End longitude', 'number'],
  ['ambient_temperature_C', 'Ambient temperature (°C)', 'number'],
  ['wire_temperature_C', 'Wire temperature (°C)', 'number'],
  ['wind_speed_m_s', 'Wind speed (m/s)', 'number'],
  ['weather', 'Weather', 'text'],
  ['scenario_name', 'Journey/scenario name', 'text'],
]

/**
 * Provides an interface to view and manage journey logs and audit exports.
 *
 * @component
 * @param {Object} props - The component props.
 * @param {string} [props.activeJourneyId] - The ID of the currently active journey to select by default.
 * @param {Function} props.onClose - Callback function invoked to close the journey logs view.
 * @returns {JSX.Element} The rendered JourneyLogs component.
 */
export default function JourneyLogs({ activeJourneyId, onClose }) {
  const closeRef = useRef(null)
  const dialogRef = useRef(null)
  const formJourneyRef = useRef('')
  const [journeys, setJourneys] = useState([])
  const [selectedId, setSelectedId] = useState(activeJourneyId ?? '')
  const [includeArchived, setIncludeArchived] = useState(false)
  const [form, setForm] = useState({})
  const [status, setStatus] = useState('Loading journey catalogue…')
  const [deleteMode, setDeleteMode] = useState(false)
  const [deleteConfirmation, setDeleteConfirmation] = useState('')
  const [recordPage, setRecordPage] = useState(null)
  const [recordQuery, setRecordQuery] = useState(null)
  const [recordHistory, setRecordHistory] = useState([])

  const selected = useMemo(
    () => journeys.find((journey) => journey.id === selectedId) ?? journeys[0],
    [journeys, selectedId],
  )

  /**
   * Fetches the journey catalogue and updates the state.
   *
   * @async
   * @function load
   * @param {boolean} [announce=false] - Whether to announce the result in the status message.
   * @returns {Promise<void>}
   */
  const load = async (announce = false) => {
    try {
      const data = await fetchJourneys(includeArchived)
      setJourneys(data.journeys)
      const preferred = data.journeys.find((item) => item.id === activeJourneyId) ?? data.journeys[0]
      if (!formJourneyRef.current && preferred) {
        formJourneyRef.current = preferred.id
        setSelectedId(preferred.id)
        setForm(preferred.metadata)
      }
      if (announce) setStatus(`${data.journeys.length} journey logs loaded.`)
      else setStatus('Journey catalogue ready.')
    } catch (error) {
      setStatus(String(error))
    }
  }

  useEffect(() => {
    const previousFocus = document.activeElement
    closeRef.current?.focus()
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
      if (event.key !== 'Tab') return
      const focusable = dialogRef.current?.querySelectorAll(
        'button:not(:disabled), a[href], input:not(:disabled)',
      )
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      previousFocus?.focus()
    }
  }, [onClose])

  useEffect(() => {
    const initial = window.setTimeout(() => load(true), 0)
    const timer = window.setInterval(() => load(false), 3000)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeArchived, activeJourneyId])

  /**
   * Selects a journey to view its details.
   *
   * @function selectJourney
   * @param {Object} journey - The journey object to select.
   * @returns {void}
   */
  const selectJourney = (journey) => {
    formJourneyRef.current = journey.id
    setSelectedId(journey.id)
    setForm(journey.metadata)
    setDeleteMode(false)
    setDeleteConfirmation('')
    setRecordPage(null)
    setRecordQuery(null)
    setRecordHistory([])
  }

  /**
   * Loads a specific page of records for the selected journey.
   *
   * @async
   * @function viewRecords
   * @param {Object} query - The record query details containing the label and source.
   * @param {number} [cursor=0] - The starting cursor for the page.
   * @param {number[]} [history=[]] - The history of cursors for navigating back.
   * @returns {Promise<void>}
   */
  const viewRecords = async (query, cursor = 0, history = []) => {
    if (!selected) return
    setStatus(`Loading ${query.label.toLowerCase()}…`)
    try {
      const page = await fetchJourneyRecords(selected.id, { ...query, cursor })
      setRecordQuery(query)
      setRecordPage(page)
      setRecordHistory(history)
      setStatus(`${page.records.length} ${query.label.toLowerCase()} loaded.`)
    } catch (error) {
      setStatus(String(error))
    }
  }

  /**
   * Saves metadata changes for the currently selected journey.
   *
   * @async
   * @function saveMetadata
   * @param {Event} event - The form submission event.
   * @returns {Promise<void>}
   */
  const saveMetadata = async (event) => {
    event.preventDefault()
    if (!selected) return
    setStatus('Saving journey metadata…')
    try {
      await updateJourneyMetadata(selected.id, form)
      await load(false)
      setStatus('Journey metadata saved.')
    } catch (error) {
      setStatus(String(error))
    }
  }

  /**
   * Archives the currently selected journey.
   *
   * @async
   * @function archive
   * @returns {Promise<void>}
   */
  const archive = async () => {
    setStatus('Archiving journey…')
    try {
      await archiveJourney(selected.id)
      formJourneyRef.current = ''
      setSelectedId('')
      await load(false)
      setStatus('Journey archived. Enable “Show archived” to view it.')
    } catch (error) {
      setStatus(String(error))
    }
  }

  /**
   * Permanently deletes the currently selected journey.
   *
   * @async
   * @function remove
   * @returns {Promise<void>}
   */
  const remove = async () => {
    setStatus('Permanently deleting journey…')
    try {
      await deleteJourney(selected.id, deleteConfirmation)
      formJourneyRef.current = ''
      setSelectedId('')
      await load(false)
      setStatus('Journey permanently deleted; deletion retained in the audit log.')
    } catch (error) {
      setStatus(String(error))
    }
  }

  return (
    <div className="journey-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div ref={dialogRef} className="journey-dialog" role="dialog" aria-modal="true" aria-labelledby="journey-title">
        <header className="journey-header">
          <div>
            <h2 id="journey-title">JOURNEY LOGS &amp; AUDIT EXPORTS</h2>
            <p>Persistent text-based access to complete simulation telemetry.</p>
          </div>
          <button ref={closeRef} onClick={onClose} aria-label="Close journey logs">✕</button>
        </header>
        <p className="journey-status mono" role="status" aria-live="polite">{status}</p>

        <div className="journey-layout">
          <aside className="journey-catalogue" aria-label="Journey catalogue">
            <label className="archive-filter">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(event) => setIncludeArchived(event.target.checked)}
              /> Show archived
            </label>
            {journeys.length === 0 && <p>No journeys recorded yet.</p>}
            {journeys.map((journey) => (
              <button
                key={journey.id}
                className={`journey-item ${selected?.id === journey.id ? 'selected' : ''}`}
                onClick={() => selectJourney(journey)}
                aria-pressed={selected?.id === journey.id}
              >
                <b>{journey.metadata.scenario_name}</b>
                <span>{journey.metadata.train_name} · {journey.metadata.route_name}</span>
                <span className="mono">{new Date(journey.started_at).toLocaleString()}</span>
                <span className={`journey-state ${journey.status.toLowerCase()}`}>{journey.status}</span>
              </button>
            ))}
          </aside>

          <main className="journey-detail">
            {selected ? <>
              <section aria-labelledby="journey-summary-heading">
                <h3 id="journey-summary-heading">ACCESSIBLE JOURNEY SUMMARY</h3>
                <dl className="journey-facts">
                  <Fact label="Session ID" value={selected.id} mono />
                  <Fact label="Status" value={selected.status} />
                  <Fact label="Started" value={new Date(selected.started_at).toLocaleString()} />
                  <Fact label="Samples" value={selected.sample_count} />
                  <Fact label="Events" value={selected.event_count} />
                  <Fact label="Distance" value={`${selected.summary.distance_km ?? 0} km`} />
                  <Fact label="Stored data" value={formatBytes(selected.storage?.total_bytes ?? 0)} />
                  <Fact
                    label="Command-limit duty"
                    value={`${selected.summary.controller?.command_limit_duty_pct ?? 0}%`}
                  />
                </dl>
                <ForceSummary summary={selected.summary} />
              </section>

              <section aria-labelledby="records-heading">
                <h3 id="records-heading">VIEW LOGGED DATA</h3>
                <p className="journey-help">
                  Browse bounded text pages without loading the complete journey into this device.
                </p>
                <div className="journey-view-actions" role="group" aria-label="Choose log data to view">
                  {RECORD_VIEWS.map((query) => (
                    <button
                      key={query.label}
                      onClick={() => viewRecords(query)}
                      aria-pressed={recordQuery?.label === query.label}
                    >
                      {query.label}
                    </button>
                  ))}
                </div>
                {recordPage && <RecordBrowser
                  page={recordPage}
                  label={recordQuery.label}
                  canGoBack={recordHistory.length > 0}
                  onBack={() => {
                    const previous = recordHistory[recordHistory.length - 1]
                    viewRecords(recordQuery, previous, recordHistory.slice(0, -1))
                  }}
                  onNext={() => viewRecords(
                    recordQuery,
                    recordPage.next_cursor,
                    [...recordHistory, recordPage.cursor],
                  )}
                />}
              </section>

              <section aria-labelledby="export-heading">
                <h3 id="export-heading">DOWNLOAD DATA</h3>
                <ul className="export-guide">
                  <li><b>CSV:</b> flat telemetry for spreadsheets and analysis tools.</li>
                  <li><b>JSON:</b> complete nested journey, event, and telemetry records.</li>
                  <li><b>Audit package:</b> both formats plus constants, summary, data dictionary, manifest, and integrity hashes.</li>
                </ul>
                <div className="journey-downloads">
                  {['csv', 'json', 'audit'].map((format) => (
                    <a
                      key={format}
                      href={journeyExportUrl(selected.id, format)}
                      download
                      onClick={() => setStatus(`${format.toUpperCase()} download requested.`)}
                    >
                      {format === 'audit' ? 'AUDIT PACKAGE (.ZIP)' : `${format.toUpperCase()} EXPORT`}
                    </a>
                  ))}
                </div>
              </section>

              <section aria-labelledby="metadata-heading">
                <h3 id="metadata-heading">JOURNEY DOCUMENTATION</h3>
                <form className="journey-form" onSubmit={saveMetadata}>
                  {FIELDS.map(([name, label, type]) => (
                    <label key={name}>
                      <span>{label}</span>
                      <input
                        name={name}
                        type={type}
                        step={type === 'number' ? 'any' : undefined}
                        value={form[name] ?? ''}
                        onChange={(event) => setForm({
                          ...form,
                          [name]: type === 'number' ? Number(event.target.value) : event.target.value,
                        })}
                      />
                    </label>
                  ))}
                  <button type="submit">SAVE DOCUMENTATION</button>
                </form>
              </section>

              {selected.status !== 'RUNNING' && <section className="journey-management" aria-labelledby="management-heading">
                <h3 id="management-heading">RETENTION</h3>
                {!selected.archived && <button onClick={archive}>ARCHIVE JOURNEY</button>}
                {!deleteMode ? (
                  <button className="delete-reveal" onClick={() => setDeleteMode(true)}>DELETE PERMANENTLY…</button>
                ) : (
                  <div className="delete-confirm">
                    <label>
                      <span>Type the complete session ID to confirm deletion</span>
                      <input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} />
                    </label>
                    <button disabled={deleteConfirmation !== selected.id} onClick={remove}>CONFIRM PERMANENT DELETE</button>
                    <button onClick={() => setDeleteMode(false)}>CANCEL</button>
                  </div>
                )}
              </section>}
            </> : <p>Select a journey to view its audit record.</p>}
          </main>
        </div>
      </div>
    </div>
  )
}

/**
 * Renders a data fact as a description list item.
 *
 * @component
 * @param {Object} props - The component props.
 * @param {string} props.label - The label for the fact.
 * @param {string|number} [props.value] - The value of the fact.
 * @param {boolean} [props.mono] - Whether to use a monospace font for the value.
 * @returns {JSX.Element} The rendered Fact component.
 */
function Fact({ label, value, mono }) {
  return <div><dt>{label}</dt><dd className={mono ? 'mono' : ''}>{value ?? '—'}</dd></div>
}

/**
 * Renders a summary table of the contact forces.
 *
 * @component
 * @param {Object} props - The component props.
 * @param {Object} [props.summary] - The summary data object containing force statistics.
 * @returns {JSX.Element} The rendered ForceSummary component.
 */
function ForceSummary({ summary }) {
  const lanes = summary?.lanes
  if (!lanes) return <p>Summary will be finalized when the journey ends.</p>
  return (
    <table className="journey-force-table">
      <caption>Contact-force audit summary</caption>
      <thead><tr><th>Metric</th><th>Passive</th><th>AeroPINN</th></tr></thead>
      <tbody>
        <tr><th>Mean force</th><td>{lanes.passive.mean_contact_force_N} N</td><td>{lanes.aeropinn.mean_contact_force_N} N</td></tr>
        <tr><th>Force standard deviation</th><td>{lanes.passive.std_contact_force_N} N</td><td>{lanes.aeropinn.std_contact_force_N} N</td></tr>
        <tr><th>Contact loss</th><td>{lanes.passive.contact_loss_pct}%</td><td>{lanes.aeropinn.contact_loss_pct}%</td></tr>
      </tbody>
    </table>
  )
}

const RECORD_VIEWS = [
  { label: 'EVENTS', source: 'events' },
  { label: 'PHYSICS 1 KHZ', source: 'telemetry', stream: 'physics_audit_1khz' },
  { label: 'CONSTANTS 1 HZ', source: 'telemetry', stream: 'configuration_snapshot_1hz' },
  { label: 'DASHBOARD FRAMES', source: 'telemetry', stream: 'dashboard_frame_30hz' },
]

/**
 * Provides a paginated browser for viewing log records.
 *
 * @component
 * @param {Object} props - The component props.
 * @param {Object} props.page - The current page of records.
 * @param {string} props.label - The label for the record view.
 * @param {boolean} props.canGoBack - Whether the user can navigate to the previous page.
 * @param {Function} props.onBack - Callback invoked to navigate back.
 * @param {Function} props.onNext - Callback invoked to navigate to the next page.
 * @returns {JSX.Element} The rendered RecordBrowser component.
 */
function RecordBrowser({ page, label, canGoBack, onBack, onNext }) {
  return (
    <div className="record-browser" aria-live="polite">
      <div className="record-browser-heading">
        <b>{label}</b>
        <span className="mono">Page offset {page.cursor.toLocaleString()} bytes</span>
      </div>
      {page.records.length === 0 ? <p>No records in this page.</p> : (
        <ol className="record-list">
          {page.records.map((record, index) => (
            <RecordItem key={`${record.recorded_at}-${index}`} record={record} />
          ))}
        </ol>
      )}
      <div className="record-pagination" aria-label="Log page navigation">
        <button disabled={!canGoBack} onClick={onBack}>PREVIOUS PAGE</button>
        <button disabled={page.next_cursor == null} onClick={onNext}>NEXT PAGE</button>
      </div>
    </div>
  )
}

/**
 * Renders an individual record item with summary metrics and raw data.
 *
 * @component
 * @param {Object} props - The component props.
 * @param {Object} props.record - The record data object.
 * @returns {JSX.Element} The rendered RecordItem component.
 */
function RecordItem({ record }) {
  const physics = record.physics
  const constants = record.constants
  const telemetry = record.telemetry
  const simulationTime = physics?.t_s ?? telemetry?.t ?? record.details?.simulation_t_s
  const title = record.event_type ?? (
    record.stream === 'physics_audit_1khz'
      ? 'Physics sample'
      : record.stream === 'configuration_snapshot_1hz'
        ? 'Configuration snapshot'
        : 'Dashboard frame'
  )
  return (
    <li>
      <div className="record-summary">
        <b>{title}</b>
        <span className="mono">Simulation {simulationTime ?? '—'} s</span>
        <span>{new Date(record.recorded_at).toLocaleString()}</span>
      </div>
      {physics && <dl className="record-metrics">
        <Fact label="Speed" value={`${physics.speed_kmh} km/h`} />
        <Fact label="Passive force" value={`${physics.passive.contact_force_N.toFixed(2)} N`} />
        <Fact label="AeroPINN force" value={`${physics.aeropinn.contact_force_N.toFixed(2)} N`} />
        <Fact label="Command" value={`${physics.aeropinn.command_force_N.toFixed(2)} N`} />
      </dl>}
      {constants && <dl className="record-metrics">
        <Fact label="Setpoint" value={`${constants.controller.setpoint_N} N`} />
        <Fact label="Integration step" value={`${constants.solver.integration_step_s} s`} />
        <Fact label="Contact tension" value={`${constants.distributed_catenary.contact_tension} N`} />
        <Fact label="Actuator response" value={`${constants.actuator.response_time} s`} />
      </dl>}
      <details>
        <summary>View complete raw record</summary>
        <pre>{JSON.stringify(record, null, 2)}</pre>
      </details>
    </li>
  )
}

/**
 * Formats a byte count into a human-readable string with units.
 *
 * @function formatBytes
 * @param {number} bytes - The number of bytes.
 * @returns {string} The formatted byte string.
 */
function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[index]}`
}
