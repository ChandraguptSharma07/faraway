import { useThrottledFrame } from '../hooks/useTelemetry'
import './ControlHealth.css'

// Monospaced HUD readouts + the live scoreboard (std dev and % arc time, passive
// vs AeroPINN — the two headline metrics).
export default function Readouts({ frameRef }) {
  const f = useThrottledFrame(frameRef, 12)
  const p = f && f.passive
  const a = f && f.aeropinn
  const beyond = f && (f.speed_kmh > 300 || f.tension_factor < 1 || f.turbulence_gain > 1)
  const timing = f && f.control_timing
  const estimate = f && f.state_estimation

  return (
    <div className="readouts">
      <div className="ro-top">
        <Stat label="TRAIN SPEED" value={f ? f.speed_kmh.toFixed(0) : '—'} unit="km/h"
              warn={beyond} />
        <Stat label="CONTROL P99" value={timing ? timing.latency_p99_ms.toFixed(2) : '—'} unit="ms"
              warn={timing && timing.latency_p99_ms > timing.period_ms} />
        <Stat label="DEADLINE MISS" value={timing ? timing.deadline_miss_pct.toFixed(1) : '—'} unit="%"
              warn={timing && timing.deadline_miss_pct > 0} accent={timing && timing.deadline_miss_pct === 0} />
        <Stat label="OPERATING POINT" value={f ? (f.operating_status ?? (beyond ? 'OUTSIDE_ENVELOPE' : 'NOMINAL')).replace('_', ' ') : '—'}
              text warn={beyond} ariaLive="polite" />
      </div>

      <div className="compare-card">
        <div className="compare-head">
          <span>HEADLINE</span><span className="passive-h">PASSIVE</span><span className="aero-h">AeroPINN*</span>
        </div>
        <CompareRow label="FORCE σ" pv={p ? p.std.toFixed(1) : '—'} av={a ? a.std.toFixed(1) : '—'} unit="N" />
        <CompareRow label="ARC TIME" pv={p ? p.arc_pct.toFixed(1) : '—'} av={a ? a.arc_pct.toFixed(1) : '—'} unit="%"
                    pDanger={p && p.arc_pct > 0.05} aDanger={a && a.arc_pct > 0.05} />
        <div className={`actuator-health mono ${estimate?.fallback_active ? 'fallback' : ''}`}
             title="Control uses delayed noisy sensors, an EKF state estimate, and the displayed simulated actuator">
          <span className="idealized">* SENSOR + EKF + ACTUATOR SIMULATION</span>
          <span>EKF <b>{estimate ? estimate.status : '—'}{Number.isFinite(estimate?.packet_age_ms) ? ` · ${estimate.packet_age_ms.toFixed(0)} ms` : ''}</b></span>
          <span>CMD <b>{Number.isFinite(a?.f_command) ? a.f_command.toFixed(0) : '—'} N</b></span>
          <span>APPLIED <b>{Number.isFinite(a?.f_actuator_estimate) ? a.f_actuator_estimate.toFixed(0) : '—'} N</b></span>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, unit, accent, warn, text, ariaLive }) {
  const cls = ['stat']
  if (accent) cls.push('accent')
  if (warn) cls.push('warn')
  return (
    <div className={cls.join(' ')} aria-live={ariaLive}>
      <div className="stat-label">{label}</div>
      <div className="stat-value mono">
        {value}{!text && <span className="stat-unit"> {unit}</span>}
        {warn && <span className="sr-only"> (Warning)</span>}
      </div>
    </div>
  )
}

function CompareRow({ label, pv, av, unit, pDanger, aDanger }) {
  return (
    <div className="compare-row">
      <span className="compare-label">{label}</span>
      <span className={`compare-value passive ${pDanger ? 'danger' : ''}`}>
        <b className="mono">{pv}</b> {unit}
        {pDanger && <span className="sr-only"> (Danger)</span>}
      </span>
      <span className={`compare-value aero ${aDanger ? 'danger' : ''}`}>
        <b className="mono">{av}</b> {unit}
        {aDanger && <span className="sr-only"> (Danger)</span>}
      </span>
    </div>
  )
}
