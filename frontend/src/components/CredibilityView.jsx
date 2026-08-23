import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import './ShadowValidation.css'
import {
  METRIC_LABELS,
  METRIC_UNITS,
  fetchCalibrationStatus,
  fetchModalCalibration,
  fetchOverlay,
  fetchShadowValidation,
  fetchValidation,
} from '../lib/api'

// The credibility panel: EN 50318 validation table (metrics inside the standard's
// ranges) + PINN-vs-solver overlay + timing comparison. The headline shot.
/**
 * The credibility panel component displaying EN 50318 validation metrics,
 * PINN vs solver overlay charts, and shadow validation reports.
 *
 * @param {Object} props - The component props.
 * @param {Function} props.onClose - Callback to close the credibility panel.
 * @returns {JSX.Element} The CredibilityView component.
 */
export default function CredibilityView({ onClose }) {
  const [val, setVal] = useState(null)
  const [ov, setOv] = useState(null)
  const [shadow, setShadow] = useState(null)
  const [modalShadow, setModalShadow] = useState(null)
  const [calibration, setCalibration] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let active = true
    let timer
    Promise.all([fetchValidation(), fetchOverlay(300), fetchCalibrationStatus()])
      .then(([v, o, c]) => { if (active) { setVal(v); setOv(o); setCalibration(c) } })
      .catch((e) => { if (active) setErr(String(e)) })

    const pollShadow = () => Promise.all([
      fetchShadowValidation(),
      fetchModalCalibration(),
    ])
      .then(([data, modalData]) => {
        if (!active) return
        setShadow(data)
        setModalShadow(modalData)
        const warming = Object.values(data.scenarios).some((row) => row.status === 'WARMING_UP') ||
                        Object.values(modalData.scenarios).some((row) => row.status === 'WARMING_UP')
        if (warming) timer = window.setTimeout(pollShadow, 1500)
      })
      .catch((e) => { if (active) setErr(String(e)) })
    pollShadow()
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [])

  return (
    <div className="cred-backdrop" onClick={onClose}>
      <div className="cred-panel" onClick={(e) => e.stopPropagation()}>
        <header className="cred-header">
          <div>
            <h2>VALIDATION &amp; CREDIBILITY</h2>
            <p className="cred-sub">Reduced model vs EN 50318 · distributed model in shadow mode</p>
          </div>
          <button className="cred-close" onClick={onClose} aria-label="Close">✕</button>
        </header>

        {err && <p className="cred-err">{err} — is the backend running on :8000?</p>}

        <div className="cred-body">
          <section className="cred-claim-boundary">
            <h3>PHYSICAL FIDELITY STATUS</h3>
            {calibration ? (
              <div className="claim-boundary-card">
                <b className="mono">{calibration.status.replaceAll('_', ' ')}</b>
                <span>Next gate: {calibration.next_gate.replaceAll('_', ' ')}</span>
                <span>Visual train geometry is not physical identification.</span>
              </div>
            ) : <Loading />}
          </section>

          <section className="cred-shadow">
            <h3>LIVE MODAL MODEL · CROSS-MODEL CONSISTENCY</h3>
            <p className="shadow-note">
              Comparing the live 36-mode catenary with the implicit distributed reference.
              Agreement is numerical consistency—not physical validation.
            </p>
            {modalShadow ? (
              <div className="shadow-grid">
                {['250', '300'].map((speed) => (
                  <ShadowCard key={speed} report={modalShadow.scenarios[speed]} col1="LIVE (36-MODE)" />
                ))}
              </div>
            ) : <Loading />}
          </section>

          <section className="cred-shadow">
            <h3>DISTRIBUTED MODEL · SHADOW VALIDATION</h3>
            <p className="shadow-note">
              Controller still uses the reduced model. Agreement is consistency evidence—not certification.
            </p>
            {shadow ? (
              <div className="shadow-grid">
                {['250', '300'].map((speed) => (
                  <ShadowCard key={speed} report={shadow.scenarios[speed]} />
                ))}
              </div>
            ) : <Loading />}
          </section>

          <section className="cred-validation">
            <h3>EN 50318 REFERENCE CHECK</h3>
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
                <BigNum label="PINN P99" value={ov.pinn_latency_ms_p99.toFixed(2)} unit="ms" accent />
                <BigNum label="SOLVER STEP" value={ov.solver_step_ms.toFixed(2)} unit="ms" />
                <BigNum label="DEADLINE MISSES" value={ov.deadline_miss_pct.toFixed(1)} unit="% @ 4 ms" />
              </div>
            </> : <Loading />}
          </section>
        </div>
      </div>
    </div>
  )
}

/**
 * Renders a validation table for a specific speed, checking metrics against EN 50318 ranges.
 *
 * @param {Object} props - The component props.
 * @param {string} props.speed - The simulation speed in km/h.
 * @param {Object} props.data - The validation data containing rows of metrics.
 * @param {Array<Object>} props.data.rows - Array of metric rows.
 * @returns {JSX.Element} The validation table component.
 */
function ValTable({ speed, data }) {
  const allPass = data.rows.every((r) => r.pass)
  return (
    <div className="val-table" role="table" aria-label={`EN 50318 Validation ${speed} km/h`}>
      <div className="val-th" role="row">
        <span role="columnheader">{speed} km/h</span>
        <span className={`val-badge ${allPass ? 'pass' : 'fail'}`} role="columnheader">
          {allPass ? 'IN RANGE' : 'CHECK'}
        </span>
      </div>
      {data.rows.map((r) => (
        <div className="val-row" key={r.metric} role="row">
          <span className="val-metric" role="cell">{METRIC_LABELS[r.metric]}</span>
          <span className="val-value mono" role="cell">{r.value}{METRIC_UNITS[r.metric]}</span>
          <span className="val-range mono" role="cell">
            <span className="sr-only">Range: </span>
            {r.low === r.high ? '0' : `${r.low}–${r.high}`}
          </span>
          <span className={`val-dot ${r.pass ? 'pass' : 'fail'}`} role="cell">
            <span className="sr-only">{r.pass ? 'Pass' : 'Fail'}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

/**
 * Renders a high-performance uPlot chart comparing the PINN prediction against the classical solver.
 *
 * @param {Object} props - The component props.
 * @param {Object} props.ov - The overlay chart data.
 * @param {Array<number>} props.ov.t - Array of time values.
 * @param {Array<number>} props.ov.f_solver - Array of classical solver force values.
 * @param {Array<number>} props.ov.f_pinn - Array of PINN prediction force values.
 * @returns {JSX.Element} The overlay chart component.
 */
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
        <span><i className="sw solver" /> reduced reference solver</span>
        <span><i className="sw pinn" /> PINN prediction (5 ms ahead)</span>
      </div>
    </div>
  )
}

/**
 * Renders a shadow validation report card for a specific speed scenario, comparing reduced vs distributed models.
 *
 * @param {Object} props - The component props.
 * @param {Object} props.report - The shadow validation report data.
 * @param {string} props.report.status - The current status of the report (e.g., 'WARMING_UP', 'ERROR').
 * @param {string|number} props.report.speed_kmh - The speed in km/h for this report.
 * @param {string} [props.report.error] - Optional error message if status is 'ERROR'.
 * @param {Object} [props.report.metrics] - Key metrics comparing legacy vs distributed models.
 * @param {Array<Object>} [props.report.gates] - Validation gates with pass/fail status.
 * @param {string} [props.report.scope] - The scope of the shadow validation.
 * @param {string} [props.report.source_commit] - The source commit hash.
 * @param {string} [props.col1] - Optional label override for the primary comparison column.
 * @returns {JSX.Element} The shadow card component.
 */
function ShadowCard({ report, col1 }) {
  const stateClass = report.status.toLowerCase().replace('_', '-')
  if (report.status === 'WARMING_UP' || report.status === 'ERROR') {
    return (
      <div className="shadow-card">
        <div className="shadow-head">
          <b>{report.speed_kmh} km/h</b>
          <span className={`shadow-status ${stateClass}`}>{report.status.replace('_', ' ')}</span>
        </div>
        <div className="shadow-wait mono">
          {report.error || 'distributed solver running outside live control loop…'}
        </div>
      </div>
    )
  }

  const keyMetrics = ['mean_N', 'std_N', 'loss_of_contact_pct']
  return (
    <div className="shadow-card" role="table" aria-label={`Shadow Validation ${report.speed_kmh} km/h`}>
      <div className="shadow-head">
        <b>{report.speed_kmh} km/h</b>
        <span className={`shadow-status ${stateClass}`}>{report.status}</span>
      </div>
      <div className="shadow-model-head mono" role="row">
        <span role="columnheader">METRIC</span>
        <span role="columnheader">{col1 || 'REDUCED'}</span>
        <span role="columnheader">DISTRIBUTED</span>
        <span role="columnheader">Δ</span>
      </div>
      {keyMetrics.map((key) => {
        const metric = report.metrics[key]
        return (
          <div className="shadow-metric mono" key={key} role="row">
            <span role="cell">{METRIC_LABELS[key]}</span>
            <span role="cell">{metric.legacy.toFixed(1)}{METRIC_UNITS[key]}</span>
            <span role="cell">{metric.distributed.toFixed(1)}{METRIC_UNITS[key]}</span>
            <span role="cell">{metric.difference_pct.toFixed(1)}%</span>
          </div>
        )
      })}
      <div className="shadow-gates">
        {report.gates.map((gate) => (
          <span className={gate.pass ? 'pass' : 'fail'} key={gate.name} title={`${gate.value} / ${gate.limit} ${gate.unit}`}>
            <i />{gate.name}
          </span>
        ))}
      </div>
      <div className="shadow-scope mono">
        {report.scope} · commit {report.source_commit.slice(0, 7)}
      </div>
    </div>
  )
}

/**
 * Displays a large emphasized number with a label and optional unit.
 *
 * @param {Object} props - The component props.
 * @param {string} props.label - The description label for the number.
 * @param {number|string} props.value - The numerical value to display.
 * @param {string} [props.unit] - An optional unit string.
 * @param {boolean} [props.accent] - If true, applies an accent styling.
 * @returns {JSX.Element} The big number display component.
 */
function BigNum({ label, value, unit, accent }) {
  return (
    <div className={`bignum ${accent ? 'accent' : ''}`}>
      <div className="bignum-label">{label}</div>
      <div className="bignum-value mono">{value}<span className="bignum-unit"> {unit}</span></div>
    </div>
  )
}

/**
 * A simple loading indicator component.
 *
 * @returns {JSX.Element} The loading component.
 */
const Loading = () => <div className="cred-loading mono">computing…</div>
