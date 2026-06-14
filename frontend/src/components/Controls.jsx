import { useEffect, useRef, useState } from 'react'

// Operator console. Sliders send live updates; presets tween the sliders so the
// actuation is visible on camera (cause -> effect). GUST injects a transient.
export default function Controls({ send }) {
  const [speed, setSpeed] = useState(250)
  const [tension, setTension] = useState(1.0)
  const [turb, setTurb] = useState(1.0)
  const [gustFlash, setGustFlash] = useState(false)
  const tweenRef = useRef(null)

  useEffect(() => () => clearInterval(tweenRef.current), [])

  const onSpeed = (v) => { setSpeed(v); send({ type: 'speed', value: v }) }
  const onTension = (v) => { setTension(v); send({ type: 'tension', value: v }) }
  const onTurb = (v) => { setTurb(v); send({ type: 'turbulence', value: v }) }

  const gust = () => {
    send({ type: 'gust', value: 80 })
    setGustFlash(true)
    setTimeout(() => setGustFlash(false), 350)
  }

  // tween all three sliders toward a target over ~1.1 s for on-camera actuation
  const applyPreset = (tgt) => {
    clearInterval(tweenRef.current)
    const start = { speed, tension, turb }
    const t0 = performance.now()
    const dur = 1100
    tweenRef.current = setInterval(() => {
      const k = Math.min(1, (performance.now() - t0) / dur)
      const e = 1 - Math.pow(1 - k, 3) // ease-out
      onSpeed(Math.round(start.speed + (tgt.speed - start.speed) * e))
      onTension(+(start.tension + (tgt.tension - start.tension) * e).toFixed(2))
      onTurb(+(start.turb + (tgt.turb - start.turb) * e).toFixed(2))
      if (k >= 1) clearInterval(tweenRef.current)
    }, 30)
  }

  return (
    <div className="controls">
      <div className="ctrl-presets">
        <button className="preset" onClick={() => applyPreset({ speed: 250, tension: 1.0, turb: 1.0 })}>
          ◇ EN 50318 VALIDATED
        </button>
        <button className="preset danger" onClick={() => applyPreset({ speed: 350, tension: 0.5, turb: 3.5 })}>
          ▲ BEYOND ENVELOPE
        </button>
      </div>

      <Slider label="SPEED" value={speed} min={80} max={400} step={1} unit="km/h"
              onChange={onSpeed} mark={300} markLabel="envelope" />
      <Slider label="CONTACT-WIRE TENSION" value={tension} min={0.3} max={1.0} step={0.01}
              unit="" fmt={(v) => (v * 100).toFixed(0) + '%'} invert onChange={onTension} />
      <Slider label="TURBULENCE" value={turb} min={0.5} max={4.0} step={0.05}
              unit="×" onChange={onTurb} />

      <button className={`gust-btn ${gustFlash ? 'flash' : ''}`} onClick={gust}>
        GUST
      </button>
    </div>
  )
}

function Slider({ label, value, min, max, step, unit, fmt, onChange, mark, markLabel }) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div className="slider">
      <div className="slider-top">
        <span className="slider-label">{label}</span>
        <span className="slider-value mono">{fmt ? fmt(value) : `${value}${unit ? ' ' + unit : ''}`}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ '--pct': pct + '%' }}
        aria-label={label}
      />
    </div>
  )
}
