import { useEffect, useRef, useState } from 'react'
import './App.css'

// Step 0 throwaway spine: connect to the FastAPI WebSocket and display the live
// counter. Proves the backend<->frontend round-trip. Replaced in Step 6.
const WS_URL = 'ws://127.0.0.1:8000/ws/spine'

function App() {
  const [status, setStatus] = useState('connecting')
  const [counter, setCounter] = useState(null)
  const [rate, setRate] = useState(0)
  const lastRef = useRef({ t: null, n: 0 })

  useEffect(() => {
    const ws = new WebSocket(WS_URL)
    ws.onopen = () => setStatus('connected')
    ws.onclose = () => setStatus('disconnected')
    ws.onerror = () => setStatus('error')
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      setCounter(msg.counter)
      const prev = lastRef.current
      if (prev.t != null) {
        const dt = msg.t - prev.t
        if (dt > 0) setRate(Math.round((msg.counter - prev.n) / dt))
      }
      lastRef.current = { t: msg.t, n: msg.counter }
    }
    return () => ws.close()
  }, [])

  return (
    <main className="spine">
      <h1>AeroPINN</h1>
      <p className="sub">backend ↔ frontend spine check</p>
      <div className={`badge ${status}`}>{status}</div>
      <div className="counter">{counter ?? '—'}</div>
      <div className="rate">{rate} msg/s</div>
    </main>
  )
}

export default App
