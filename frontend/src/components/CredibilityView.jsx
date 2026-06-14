import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { METRIC_LABELS, METRIC_UNITS, fetchOverlay, fetchValidation } from '../lib/api'

// The credibility panel: EN 50318 validation table (metrics inside the standard's
// ranges) + PINN-vs-solver overlay + timing comparison. The headline shot.
export default function CredibilityView({ onClose }) {
  const [val, setVal] = useState(null)
  const [ov, setOv] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    Promise.all([fetchValidation(), fetchOverlay(300)])
      .then(([v, o]) => { setVal(v); setOv(o) })
      .catch((e) => setErr(String(e)))
  }, [])

  return (
    <div className="cred-backdrop" onClick={onClose}>
      <div className="cred-panel" onClick={(e) => e.stopPropagation()}>
        <header className="cred-header">
          <div>
            <h2>VALIDATION &amp; CREDIBILITY</h2>
            <p className="cred-sub">Classical solver vs EN 50318 · PINN predictor vs classical solver</p>
          </div>
          <button className="cred-close" onClick={onClose} aria-label="Close">✕</button>
        </header>

        {err && <p className="cred-err">{err} — is the backend running on :8000?</p>}

        <div className="cred-body">
          <section className="cred-validation">
            <h3>EN 50318 VALIDATION</h3>
            {val ? ['250', '300'].map((sp) => (
              <ValTable key={sp} speed={sp} data={val[sp]} />
            )) : <Loading />}
          </section>

          <section className="cred-overlay">
            <h3>PINN PREDICTION vs CLASSICAL SOLVER</h3>
            {ov ? <>
              <OverlayChart ov={ov} />
              <div className="cred-numbers">
                <BigNum label="PREDICTION ERROR" value={ov.rmse_N.toFixed(2)} unit="N RMSE" accent />
                <BigNum label="PINN INFERENCE" value={ov.pinn_latency_ms_single.toFixed(2)} unit="ms" accent />
                <BigNum label="SOLVER STEP" value={ov.solver_step_ms.toFixed(2)} unit="ms" />
                <BigNum label="HORIZON" value={(ov.horizon_ms ?? 5).toFixed(0)} unit="ms ahead" />
              </div>
            </> : <Loading />}
          </section>
        </div>
      </div>
    </div>
  )
}

function ValTable({ speed, data }) {
  const allPass = data.rows.every((r) => r.pass)
  return (
    <div className="val-table">
      <div className="val-th">
        <span>{speed} km/h</span>
        <span className={`val-badge ${allPass ? 'pass' : 'fail'}`}>
          {allPass ? 'VALIDATED' : 'CHECK'}
        </span>
      </div>
      {data.rows.map((r) => (
        <div className="val-row" key={r.metric}>
          <span className="val-metric">{METRIC_LABELS[r.metric]}</span>
          <span className="val-value mono">{r.value}{METRIC_UNITS[r.metric]}</span>
          <span className="val-range mono">
            {r.low === r.high ? '0' : `${r.low}–${r.high}`}
          </span>
          <span className={`val-dot ${r.pass ? 'pass' : 'fail'}`} />
        </div>
      ))}
    </div>
  )
}

function OverlayChart({ ov }) {
  const ref = useRef(null)
  useEffect(() => {
    const wrap = ref.current
    const opts = {
      width: wrap.clientWidth, height: 220,
      padding: [10, 10, 4, 6],
      cursor: { show: false }, legend: { show: false },
      scales: { x: { time: false } },
      axes: [
        { stroke: '#4d5a6b', grid: { stroke: 'rgba(255,255,255,0.04)' },
          values: (u, v) => v.map((x) => x.toFixed(1) + 's'), font: '11px JetBrains Mono, monospace' },
        { stroke: '#4d5a6b', grid: { stroke: 'rgba(255,255,255,0.04)' },
          values: (u, v) => v.map((x) => x + 'N'), font: '11px JetBrains Mono, monospace' },
      ],
      series: [
        {},
        { label: 'Solver', stroke: 'rgba(180,195,210,0.9)', width: 3, points: { show: false } },
        { label: 'PINN', stroke: '#2ee6d6', width: 1.4, dash: [5, 3], points: { show: false } },
      ],
    }
    const u = new uPlot(opts, [ov.t, ov.f_solver, ov.f_pinn], wrap)
    const ro = new ResizeObserver(() => u.setSize({ width: wrap.clientWidth, height: 220 }))
    ro.observe(wrap)
    return () => { ro.disconnect(); u.destroy() }
  }, [ov])

  return (
    <div className="overlay-chart">
      <div ref={ref} />
      <div className="overlay-legend">
        <span><i className="sw solver" /> classical solver (ground truth)</span>
        <span><i className="sw pinn" /> PINN prediction (5 ms ahead)</span>
      </div>
    </div>
  )
}

function BigNum({ label, value, unit, accent }) {
  return (
    <div className={`bignum ${accent ? 'accent' : ''}`}>
      <div className="bignum-label">{label}</div>
      <div className="bignum-value mono">{value}<span className="bignum-unit"> {unit}</span></div>
    </div>
  )
}

const Loading = () => <div className="cred-loading mono">computing…</div>
