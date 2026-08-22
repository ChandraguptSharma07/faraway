import { useEffect, useRef, useState } from 'react'

/**
 * Sample the latest frame at a low rate (default ~12 Hz) for text readouts, so
 * numeric panels re-render smoothly without 50 Hz React churn.
 *
 * @param {import('react').MutableRefObject<any>} frameRef - Reference to the current frame data.
 * @param {number} [hz=12] - The throttle rate in hertz.
 * @returns {any} The throttled frame data.
 */
export function useThrottledFrame(frameRef, hz = 12) {
  const [frame, setFrame] = useState(null)
  useEffect(() => {
    let raf, last = 0
    const interval = 1000 / hz
    /**
     * Animation frame callback to update the throttled frame.
     *
     * @param {number} ts - The current timestamp.
     */
    const tick = (ts) => {
      if (ts - last >= interval) { last = ts; setFrame(frameRef.current) }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [frameRef, hz])
  return frame
}

const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const WS_URL = `${protocol}//${window.location.host}/ws`
const MAX_POINTS = 600 // ~12 s of history at 50 fps

/**
 * Live telemetry channel. Latest frame and rolling history live in refs so the
 * 60 fps canvas + streaming chart can read them without forcing React re-renders.
 *
 * @returns {{
 *   frameRef: import('react').MutableRefObject<any>,
 *   historyRef: import('react').MutableRefObject<{ t: number[], fp: number[], fa: number[], lostP: number[], lostA: number[] }>,
 *   connected: boolean,
 *   currentJourney: any,
 *   send: (msg: any) => void
 * }} The telemetry hook context containing references and connection state.
 */
export function useTelemetry() {
  const frameRef = useRef(null)
  const historyRef = useRef({ t: [], fp: [], fa: [], lostP: [], lostA: [] })
  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [currentJourney, setCurrentJourney] = useState(null)

  useEffect(() => {
    let alive = true
    let retry

    /**
     * Establishes the WebSocket connection and sets up event listeners.
     */
    const connect = () => {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws
      ws.onopen = () => alive && setConnected(true)
      ws.onclose = () => {
        if (!alive) return
        setConnected(false)
        retry = setTimeout(connect, 800)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (e) => {
        const f = JSON.parse(e.data)
        setCurrentJourney((previous) => (
          previous?.id === f.journey?.id ? previous : (f.journey ?? null)
        ))
        frameRef.current = f
        const h = historyRef.current
        h.t.push(f.t)
        h.fp.push(f.passive.contact_force)
        h.fa.push(f.aeropinn.contact_force)
        h.lostP.push(f.passive.contact_lost ? 1 : 0)
        h.lostA.push(f.aeropinn.contact_lost ? 1 : 0)
        if (h.t.length > MAX_POINTS) {
          h.t.shift(); h.fp.shift(); h.fa.shift(); h.lostP.shift(); h.lostA.shift()
        }
      }
    }
    connect()

    return () => {
      alive = false
      clearTimeout(retry)
      wsRef.current && wsRef.current.close()
    }
  }, [])

  /**
   * Sends a JSON-serialized message over the WebSocket connection.
   *
   * @param {any} msg - The message object to send.
   */
  const send = (msg) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
  }

  return { frameRef, historyRef, connected, currentJourney, send }
}
