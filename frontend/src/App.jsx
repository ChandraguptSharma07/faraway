import { useEffect, useState } from 'react'
import './App.css'
import { useTelemetry } from './hooks/useTelemetry'
import WorldCanvas from './components/WorldCanvas'
import ForceTrace from './components/ForceTrace'
import Readouts from './components/Readouts'
import Controls from './components/Controls'
import CredibilityView from './components/CredibilityView'

export default function App() {
  const { frameRef, historyRef, connected, send } = useTelemetry()
  const [showCred, setShowCred] = useState(false)
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    const m = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(m.matches)
    const h = (e) => setReduced(e.matches)
    m.addEventListener('change', h)
    return () => m.removeEventListener('change', h)
  }, [])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◈</span>
          <span className="brand-name">AeroPINN</span>
          <span className="brand-sub">active pantograph stabilization · PINN-MPC</span>
        </div>
        <div className="topbar-right">
          <button className="cred-trigger" onClick={() => setShowCred(true)}>
            VALIDATION
          </button>
          <span className={`conn ${connected ? 'on' : 'off'}`}>
            <i /> {connected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </header>

      <section className="world-zone">
        <WorldCanvas frameRef={frameRef} prefersReducedMotion={reduced} />
        {!connected && (
          <div className="world-offline mono">
            connecting to backend on :8000…
          </div>
        )}
      </section>

      <section className="instrument-zone">
        <div className="panel trace-panel">
          <div className="panel-title">CONTACT FORCE · LIVE</div>
          <ForceTrace historyRef={historyRef} />
        </div>
        <div className="panel readout-panel">
          <Readouts frameRef={frameRef} />
        </div>
        <div className="panel control-panel">
          <div className="panel-title">OPERATOR CONSOLE</div>
          <Controls send={send} />
        </div>
      </section>

      {showCred && <CredibilityView onClose={() => setShowCred(false)} />}
    </div>
  )
}
