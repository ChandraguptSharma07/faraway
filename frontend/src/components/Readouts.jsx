import { useThrottledFrame } from '../hooks/useTelemetry'

// Monospaced HUD readouts + the live scoreboard (std dev and % arc time, passive
// vs AeroPINN — the two headline metrics).
export default function Readouts({ frameRef }) {
  const f = useThrottledFrame(frameRef, 12)
  const p = f && f.passive
  const a = f && f.aeropinn
  const beyond = f && (f.speed_kmh > 300 || f.tension_factor < 1 || f.turbulence_gain > 1)

  return (
    <div className="readouts">
      <div className="ro-top">
        <Stat label="TRAIN SPEED" value={f ? f.speed_kmh.toFixed(0) : '—'} unit="km/h"
              warn={beyond} />
        <Stat label="PINN INFERENCE" value={f ? f.pinn_latency_ms.toFixed(2) : '—'} unit="ms"
              accent />
        <Stat label="SETPOINT" value={f ? f.setpoint_N.toFixed(0) : '—'} unit="N" />
        <Stat label="REGIME" value={beyond ? 'BEYOND' : 'VALIDATED'}
              text warn={beyond} ok={!beyond} />
      </div>

      <div className="compare-card">
        <div className="compare-head">
          <span>HEADLINE</span><span className="passive-h">PASSIVE</span><span className="aero-h">AeroPINN</span>
        </div>
        <CompareRow label="FORCE σ" pv={p ? p.std.toFixed(1) : '—'} av={a ? a.std.toFixed(1) : '—'} unit="N" />
        <CompareRow label="ARC TIME" pv={p ? p.arc_pct.toFixed(1) : '—'} av={a ? a.arc_pct.toFixed(1) : '—'} unit="%"
                    pDanger={p && p.arc_pct > 0.05} aDanger={a && a.arc_pct > 0.05} />
      </div>
    </div>
  )
}

function Stat({ label, value, unit, accent, warn, ok, text }) {
  const cls = ['stat']
  if (accent) cls.push('accent')
  if (warn) cls.push('warn')
  if (ok) cls.push('ok')
  return (
    <div className={cls.join(' ')}>
      <div className="stat-label">{label}</div>
      <div className="stat-value mono">
        {value}{!text && <span className="stat-unit"> {unit}</span>}
      </div>
    </div>
  )
}

function CompareRow({ label, pv, av, unit, pDanger, aDanger }) {
  return (
    <div className="compare-row">
      <span className="compare-label">{label}</span>
      <span className={`compare-value passive ${pDanger ? 'danger' : ''}`}><b className="mono">{pv}</b> {unit}</span>
      <span className={`compare-value aero ${aDanger ? 'danger' : ''}`}><b className="mono">{av}</b> {unit}</span>
    </div>
  )
}
