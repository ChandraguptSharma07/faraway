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

      <div className="scoreboard">
        <div className="sb-head"><span>HEADLINE METRICS</span></div>
        <div className="sb-grid">
          <div className="sb-corner" />
          <div className="sb-col-h passive-h">PASSIVE</div>
          <div className="sb-col-h aero-h">AeroPINN</div>

          <div className="sb-row-h">FORCE σ</div>
          <Cell v={p ? p.std.toFixed(1) : '—'} unit="N" kind="passive" />
          <Cell v={a ? a.std.toFixed(1) : '—'} unit="N" kind="aero" />

          <div className="sb-row-h">ARC TIME</div>
          <Cell v={p ? p.arc_pct.toFixed(1) : '—'} unit="%" kind="passive"
                danger={p && p.arc_pct > 0.05} />
          <Cell v={a ? a.arc_pct.toFixed(1) : '—'} unit="%" kind="aero"
                danger={a && a.arc_pct > 0.05} />
        </div>
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

function Cell({ v, unit, kind, danger }) {
  return (
    <div className={`sb-cell ${kind} ${danger ? 'danger' : ''}`}>
      <span className="mono sb-val">{v}</span>
      <span className="sb-unit">{unit}</span>
    </div>
  )
}
