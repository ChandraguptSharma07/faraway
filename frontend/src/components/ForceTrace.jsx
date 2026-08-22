import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useThrottledFrame } from '../hooks/useTelemetry'

const ACCENT = '#2ee6d6'
const PASSIVE = '#c9a24a'  // amber-grey: the jagged baseline (not red — red is fault-only)
const SETPOINT = 115

// Live contact-force trace: passive (jagged, spiking through the zero/arc threshold)
// vs AeroPINN (near-flat ribbon at the setpoint). Updated imperatively from the
// telemetry ring buffer in a rAF loop — no React re-render per sample.
export default function ForceTrace({ historyRef, frameRef }) {
  const wrapRef = useRef(null)
  const uRef = useRef(null)
  const frame = useThrottledFrame(frameRef, 8)

  useEffect(() => {
    const wrap = wrapRef.current

    const thresholds = {
      hooks: {
        draw: [(u) => {
          const { ctx } = u
          const x0 = u.bbox.left
          const x1 = u.bbox.left + u.bbox.width
          ctx.save()
          // setpoint line
          const ys = Math.round(u.valToPos(SETPOINT, 'y', true))
          ctx.strokeStyle = 'rgba(46,230,214,0.35)'
          ctx.setLineDash([4, 4]); ctx.lineWidth = 1
          ctx.beginPath(); ctx.moveTo(x0, ys); ctx.lineTo(x1, ys); ctx.stroke()
          // zero / arc threshold
          const yz = Math.round(u.valToPos(0, 'y', true))
          ctx.strokeStyle = 'rgba(255,59,59,0.5)'
          ctx.beginPath(); ctx.moveTo(x0, yz); ctx.lineTo(x1, yz); ctx.stroke()
          ctx.restore()
        }],
      },
    }

    const opts = {
      width: wrap.clientWidth,
      height: wrap.clientHeight,
      padding: [12, 12, 4, 8],
      cursor: { show: false },
      legend: { show: false },
      scales: { x: { time: false }, y: { range: [-60, 290] } },
      axes: [
        {
          stroke: '#4d5a6b', grid: { stroke: 'rgba(255,255,255,0.04)' },
          ticks: { stroke: 'rgba(255,255,255,0.06)' },
          values: (u, vals) => vals.map((v) => v.toFixed(1) + 's'),
          font: '11px JetBrains Mono, monospace',
        },
        {
          stroke: '#4d5a6b', grid: { stroke: 'rgba(255,255,255,0.04)' },
          ticks: { stroke: 'rgba(255,255,255,0.06)' },
          values: (u, vals) => vals.map((v) => v + 'N'),
          font: '11px JetBrains Mono, monospace',
        },
      ],
      series: [
        {},
        { label: 'Passive', stroke: PASSIVE, width: 1.2, points: { show: false } },
        { label: 'AeroPINN', stroke: ACCENT, width: 2.2, points: { show: false },
          fill: 'rgba(46,230,214,0.06)' },
      ],
      plugins: [thresholds],
    }

    const u = new uPlot(opts, [[0], [0], [0]], wrap)
    uRef.current = u

    const ro = new ResizeObserver(() => {
      u.setSize({ width: wrap.clientWidth, height: wrap.clientHeight })
    })
    ro.observe(wrap)

    let raf
    const tick = () => {
      const h = historyRef.current
      if (h.t.length > 1) u.setData([h.t, h.fp, h.fa])
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)

    return () => { cancelAnimationFrame(raf); ro.disconnect(); u.destroy() }
  }, [historyRef])

  const [srSummary, setSrSummary] = useState('')

  useEffect(() => {
    const interval = setInterval(() => {
      if (frameRef.current) {
        const f = frameRef.current
        setSrSummary(`Contact force: Passive ${f.passive.contact_force.toFixed(0)} N, AeroPINN ${f.aeropinn.contact_force.toFixed(0)} N.`)
      }
    }, 5000)
    return () => clearInterval(interval)
  }, [frameRef])

  return (
    <div className="trace-shell">
      <div className="sr-only" aria-live="polite">{srSummary}</div>
      <div className="trace-legend mono" aria-hidden="true">
        <span className="legend-item passive"><i />PASSIVE <b>{frame ? frame.passive.contact_force.toFixed(0) : '—'} N</b></span>
        <span className="legend-item aero"><i />AeroPINN <b>{frame ? frame.aeropinn.contact_force.toFixed(0) : '—'} N</b></span>
        <span className="legend-setpoint">SETPOINT {frame ? frame.setpoint_N.toFixed(0) : '115'} N</span>
      </div>
      <div className="trace-wrap" ref={wrapRef} aria-hidden="true" />
    </div>
  )
}
