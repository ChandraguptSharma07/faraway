import { useEffect, useRef, useState } from 'react'

// Operator console. Sliders send live updates; presets tween the sliders so the
// actuation is visible on camera (cause -> effect). GUST injects a transient.
/**
 * Operator console for controlling the simulation parameters.
 * Sliders send live updates; presets tween the sliders so the actuation is visible on camera.
 * GUST injects a transient disturbance.
 *
 * @param {Object} props - The component props.
 * @param {Function} props.send - Function to send control updates to the backend.
 * @returns {JSX.Element} The Controls component.
 */
export default function Controls({ send }) {
  const [speed, setSpeed] = useState(250)
  const [tension, setTension] = useState(1.0)
  const [turb, setTurb] = useState(1.0)
  const [gustFlash, setGustFlash] = useState(false)
  const tweenRef = useRef(null)

  useEffect(() => () => clearInterval(tweenRef.current), [])

  /**
   * Updates speed state and sends to backend.
   * @param {number} v - The new speed value.
   */
  const onSpeed = (v) => { setSpeed(v); send({ type: 'speed', value: v }) }
  /**
   * Updates tension state and sends to backend.
   * @param {number} v - The new tension value.
   */
  const onTension = (v) => { setTension(v); send({ type: 'tension', value: v }) }
  /**
   * Updates turbulence state and sends to backend.
   * @param {number} v - The new turbulence value.
   */
  const onTurb = (v) => { setTurb(v); send({ type: 'turbulence', value: v }) }

  /**
   * Triggers a transient gust disturbance and flashes the button.
   */
  const gust = () => {
    send({ type: 'gust', value: 80 })
    setGustFlash(true)
    setTimeout(() => setGustFlash(false), 350)
  }

  // tween all three sliders toward a target over ~1.1 s for on-camera actuation
  /**
   * Tweens all three sliders toward target values over ~1.1s for on-camera actuation.
   * @param {Object} tgt - Target values for speed, tension, and turb.
   */
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
          ◇ NOMINAL
        </button>
        <button className="preset danger" onClick={() => applyPreset({ speed: 350, tension: 0.5, turb: 3.5 })}>
          ▲ STRESS TEST
        </button>
      </div>

      <div className="ctrl-sliders">
        <Slider label="SPEED" value={speed} min={80} max={400} step={1} unit="km/h"
                onChange={onSpeed} />
        <Slider label="WIRE TENSION" value={tension} min={0.3} max={1.0} step={0.01}
                unit="" fmt={(v) => (v * 100).toFixed(0) + '%'} onChange={onTension} />
        <Slider label="TURBULENCE" value={turb} min={0.5} max={4.0} step={0.05}
                unit="×" onChange={onTurb} />
      </div>

      <button className={`gust-btn ${gustFlash ? 'flash' : ''}`} onClick={gust}>
        GUST
      </button>
    </div>
  )
}

/**
 * A reusable slider component with a styled range input and label.
 *
 * @param {Object} props - The component props.
 * @param {string} props.label - The label displayed above the slider.
 * @param {number} props.value - The current value of the slider.
 * @param {number} props.min - The minimum allowed value.
 * @param {number} props.max - The maximum allowed value.
 * @param {number} props.step - The step increment for the slider.
 * @param {string} [props.unit] - An optional unit string appended to the displayed value.
 * @param {Function} [props.fmt] - An optional formatting function for the displayed value.
 * @param {Function} props.onChange - Callback fired when the slider value changes.
 * @returns {JSX.Element} The Slider component.
 */
function Slider({ label, value, min, max, step, unit, fmt, onChange }) {
  const pct = ((value - min) / (max - min)) * 100
  const displayValue = fmt ? fmt(value) : `${value}${unit ? ' ' + unit : ''}`
  return (
    <div className="slider">
      <div className="slider-top">
        <span className="slider-label">{label}</span>
        <span className="slider-value mono">{displayValue}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ '--pct': pct + '%' }}
        aria-label={label}
        aria-valuetext={displayValue}
      />
    </div>
  )
}
