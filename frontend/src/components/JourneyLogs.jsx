import { useEffect, useMemo, useRef, useState } from 'react'
import {
  archiveJourney,
  deleteJourney,
  fetchJourneys,
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

  const selected = useMemo(
    () => journeys.find((journey) => journey.id === selectedId) ?? journeys[0],
    [journeys, selectedId],
  )

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

  const selectJourney = (journey) => {
    formJourneyRef.current = journey.id
    setSelectedId(journey.id)
    setForm(journey.metadata)
    setDeleteMode(false)
    setDeleteConfirmation('')
  }

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
                </dl>
                <ForceSummary summary={selected.summary} />
              </section>

              <section aria-labelledby="export-heading">
                <h3 id="export-heading">DOWNLOAD DATA</h3>
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

function Fact({ label, value, mono }) {
  return <div><dt>{label}</dt><dd className={mono ? 'mono' : ''}>{value ?? '—'}</dd></div>
}

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
