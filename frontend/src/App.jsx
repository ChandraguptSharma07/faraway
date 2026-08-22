import { lazy, Suspense, useEffect, useState } from 'react'
import './App.css'
import { useTelemetry } from './hooks/useTelemetry'
import ForceTrace from './components/ForceTrace'
import Readouts from './components/Readouts'
import Controls from './components/Controls'

const World3D = lazy(() => import('./components/World3D'))
const CredibilityView = lazy(() => import('./components/CredibilityView'))
const JourneyLogs = lazy(() => import('./components/JourneyLogs'))

export default function App() {
  const { frameRef, historyRef, connected, currentJourney, send } = useTelemetry()
  const [showCred, setShowCred] = useState(false)
  const [showJourneys, setShowJourneys] = useState(
    () => new URLSearchParams(window.location.search).get('view') === 'journeys',
  )
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [showPhysics, setShowPhysics] = useState(true)
  const [amplifyMotion, setAmplifyMotion] = useState(false)
  const [cameraReset, setCameraReset] = useState(0)

  useEffect(() => {
    const m = window.matchMedia('(prefers-reduced-motion: reduce)')
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
          <button
            className="journey-trigger"
            onClick={() => setShowJourneys(true)}
            aria-haspopup="dialog"
          >
            JOURNEY LOGS
          </button>
          <button className="cred-trigger" onClick={() => setShowCred(true)}>
            VALIDATION
          </button>
          <span className={`conn ${connected ? 'on' : 'off'}`}>
            <i /> {connected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </header>

      <section className="world-zone">
        <Suspense fallback={<div className="world3d"><div className="world3d-status mono">loading 3D renderer…</div></div>}>
          <World3D
            frameRef={frameRef}
            prefersReducedMotion={reduced}
            showPhysics={showPhysics}
            motionGain={amplifyMotion ? 25 : 1}
            cameraReset={cameraReset}
          />
        </Suspense>
        <div className="view-tools">
          <button
            className={`physics-toggle ${showPhysics ? 'on' : ''}`}
            onClick={() => setShowPhysics((v) => !v)}
            title="Toggle live force vectors"
          >
            FORCES {showPhysics ? 'ON' : 'OFF'}
          </button>
          <button
            className={`motion-toggle ${amplifyMotion ? 'on' : ''}`}
            onClick={() => setAmplifyMotion((value) => !value)}
            title="Toggle labelled visual displacement amplification; telemetry remains unscaled"
            aria-pressed={amplifyMotion}
          >
            MOTION {amplifyMotion ? '×25' : '1×'}
          </button>
          <button className="camera-reset" onClick={() => setCameraReset((v) => v + 1)}>
            RESET VIEW
          </button>
        </div>
        {!connected && (
          <div className="world-offline mono">
            connecting to backend on :8000…
          </div>
        )}
      </section>

      <section className="instrument-zone">
        <div className="kpi-strip">
          <Readouts frameRef={frameRef} />
        </div>
        <div className="panel trace-panel">
          <div className="panel-title">CONTACT FORCE · LIVE COMPARISON</div>
          <ForceTrace historyRef={historyRef} frameRef={frameRef} />
        </div>
        <div className="panel control-panel">
          <div className="panel-title">OPERATOR CONSOLE</div>
          <Controls send={send} />
        </div>
      </section>

      {showCred && (
        <Suspense fallback={null}>
          <CredibilityView onClose={() => setShowCred(false)} />
        </Suspense>
      )}
      {showJourneys && (
        <Suspense fallback={null}>
          <JourneyLogs
            activeJourneyId={currentJourney?.id}
            onClose={() => setShowJourneys(false)}
          />
        </Suspense>
      )}
    </div>
  )
}
