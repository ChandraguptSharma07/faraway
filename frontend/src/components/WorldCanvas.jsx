import { useEffect, useRef } from 'react'

// 2.5D side elevation. Two stacked lanes share exogenous geometry/disturbance but
// have independent force-driven wire states. The world scrolls at the real
// span-passing frequency (speed / span). Pantograph heads bounce per REAL backend
// displacement; the contact node glows cyan when in contact and throws a red arc
// spark on contact loss. Everything is read from refs inside a rAF loop.

const ACCENT = '#2ee6d6'
const ARC = '#ff3b3b'
const PX_PER_MM = 2.4          // gross wire-undulation magnification
const SPAN_M = 60              // physics span length
const SPAN_PX = 240            // pixels per span on screen

// Force-driven contact-wire lift: the flexible wire is pulled up by the pantograph
// by uplift = contact_force / catenary_stiffness (our EN 50318 "max uplift" metric,
// sent as sys.uplift_mm). This is the per-system signal that actually differs.
const UPLIFT_SCALE = 0.85      // px per mm of catenary uplift
const UPLIFT_MAX_PX = 65       // clamp so the lift never reaches the messenger wire
const TENT_HALF_W = 56         // px half-width of the local wire lift under the head
const LOSS_GAP_PX = 13         // head<->wire separation drawn on contact loss

// Physics-overlay scaling: free-body force arrows are drawn to real newtons.
const PX_PER_N = 0.32
const ARROW_MAX_PX = 48
const MONO = 'JetBrains Mono, ui-monospace, monospace'

export default function WorldCanvas({ frameRef, prefersReducedMotion, showPhysics = true }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    let raf
    let dpr = Math.min(window.devicePixelRatio || 1, 2)

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      const r = canvas.getBoundingClientRect()
      canvas.width = r.width * dpr
      canvas.height = r.height * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    const draw = () => {
      const r = canvas.getBoundingClientRect()
      const W = r.width
      const H = r.height
      ctx.clearRect(0, 0, W, H)

      const f = frameRef.current
      const speed_ms = f ? f.speed_kmh / 3.6 : 70
      const worldX = f ? speed_ms * f.t * (SPAN_PX / SPAN_M) : 0

      // two lanes
      const laneH = H / 2
      drawLane(ctx, W, 0, laneH, 'PASSIVE', f && f.passive, f, worldX, prefersReducedMotion, showPhysics, false)
      drawLane(ctx, W, laneH, laneH, 'AeroPINN', f && f.aeropinn, f, worldX, prefersReducedMotion, showPhysics, true)

      // divider
      ctx.strokeStyle = 'rgba(255,255,255,0.05)'
      ctx.beginPath(); ctx.moveTo(0, laneH); ctx.lineTo(W, laneH); ctx.stroke()

      if (showPhysics && f) {
        drawSpanDimension(ctx, W, H, worldX)
        drawModelCard(ctx, W, H, f)
      }

      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)

    return () => { cancelAnimationFrame(raf); ro.disconnect() }
  }, [frameRef, prefersReducedMotion, showPhysics])

  return <canvas ref={canvasRef} className="world-canvas" />
}

function drawLane(ctx, W, y0, H, label, sys, frame, worldX, reduced, showPhysics, isAero) {
  const contactX = W * 0.34
  const wireBaseY = y0 + H * 0.42
  const railY = y0 + H * 0.92

  // --- background speed streaks (subtle) ---
  if (!reduced) {
    ctx.save()
    ctx.globalAlpha = 0.04
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 1
    for (let i = 0; i < 6; i++) {
      const sy = y0 + 18 + i * (H / 8)
      const off = (worldX * 1.6 + i * 60) % 220
      ctx.beginPath()
      ctx.moveTo(W - off, sy); ctx.lineTo(W - off - 40, sy)
      ctx.stroke()
    }
    ctx.restore()
  }

  const wireMm = sys?.wire_mm ?? frame?.wire_mm ?? 0
  const lost = sys ? sys.contact_lost : false

  // Per-system contact-force lift (the discriminating signal). Collapses to 0 on loss.
  const upliftMm = sys ? (sys.uplift_mm ?? 0) : 0
  const upliftPx = lost ? 0 : Math.min(upliftMm * UPLIFT_SCALE, UPLIFT_MAX_PX)

  // Gross position includes the lane-specific force-driven catenary ripple.
  const contactNominalY = wireBaseY - wireMm * PX_PER_MM
  const apexY = contactNominalY - upliftPx

  // raised-cosine blend that tents the wire up to the apex near the contact point
  const tent = (sx) => {
    const d = Math.abs(sx - contactX)
    return d >= TENT_HALF_W ? 0 : 0.5 * (1 + Math.cos((Math.PI * d) / TENT_HALF_W))
  }

  // --- catenary: messenger wire, poles, droppers, contact wire (scrolling) ---
  const messengerY = y0 + H * 0.16
  const scroll = worldX % SPAN_PX
  ctx.lineWidth = 1.2

  // messenger (top) wire
  ctx.strokeStyle = 'rgba(120,140,160,0.35)'
  ctx.beginPath(); ctx.moveTo(0, messengerY); ctx.lineTo(W, messengerY); ctx.stroke()

  // contact wire: mid-span sag, blended near the pantograph toward the lifted apex
  // (the wire is physically pulled up by the contact force). Brighter under load.
  ctx.strokeStyle = lost ? 'rgba(255,90,90,0.7)' : 'rgba(150,170,190,0.55)'
  ctx.beginPath()
  for (let x = -SPAN_PX; x <= W + SPAN_PX; x += 5) {
    const sx = x - scroll
    const phase = ((x % SPAN_PX) + SPAN_PX) % SPAN_PX / SPAN_PX // 0..1 within span
    const sag = Math.sin(phase * Math.PI) * 10 // sag mid-span, taut at poles
    const base = wireBaseY + sag
    const b = tent(sx)
    const yy = base * (1 - b) + apexY * b // pull wire up to the apex under the head
    if (x === -SPAN_PX) ctx.moveTo(sx, yy); else ctx.lineTo(sx, yy)
  }
  ctx.stroke()

  // poles + droppers per span
  for (let k = -1; k * SPAN_PX - scroll < W + SPAN_PX; k++) {
    const px = k * SPAN_PX - scroll
    if (px < -40 || px > W + 40) continue
    // pole
    ctx.strokeStyle = 'rgba(110,128,148,0.5)'
    ctx.lineWidth = 3
    ctx.beginPath(); ctx.moveTo(px, messengerY - 14); ctx.lineTo(px, railY); ctx.stroke()
    // registration arm
    ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(px, wireBaseY - 18); ctx.lineTo(px + 16, wireBaseY); ctx.stroke()
    // droppers (messenger -> contact) within the span
    ctx.strokeStyle = 'rgba(120,140,160,0.25)'
    ctx.lineWidth = 1
    for (let d = 1; d <= 4; d++) {
      const dx = px + (d * SPAN_PX) / 5
      const phase = d / 5
      const sag = Math.sin(phase * Math.PI) * 10
      ctx.beginPath(); ctx.moveTo(dx, messengerY); ctx.lineTo(dx, wireBaseY + sag); ctx.stroke()
    }
  }

  // --- rail / ground ---
  ctx.strokeStyle = 'rgba(255,255,255,0.06)'
  ctx.lineWidth = 2
  ctx.beginPath(); ctx.moveTo(0, railY); ctx.lineTo(W, railY); ctx.stroke()

  // --- train + pantograph ---
  // In contact the head sits at the lifted wire apex; on loss it has fallen below the
  // wire (the wire snaps back to nominal) and an arc bridges the gap.
  const roofY = railY - H * 0.30
  const headY = lost ? contactNominalY + LOSS_GAP_PX : apexY

  drawTrain(ctx, contactX, railY, H)
  drawPantograph(ctx, contactX, roofY, Math.min(headY, roofY - 6))

  // --- contact node + arc ---
  const nodeColor = lost ? ARC : ACCENT
  if (lost) {
    drawArc(ctx, contactX, headY, contactNominalY, reduced)
    // red flash halo at the wire where contact tore away
    ctx.save()
    const g = ctx.createRadialGradient(contactX, contactNominalY, 0, contactX, contactNominalY, 46)
    g.addColorStop(0, 'rgba(255,59,59,0.5)')
    g.addColorStop(1, 'rgba(255,59,59,0)')
    ctx.fillStyle = g
    ctx.beginPath(); ctx.arc(contactX, contactNominalY, 46, 0, Math.PI * 2); ctx.fill()
    ctx.restore()
  }
  // glowing node at the contact point (radius grows subtly with contact load)
  ctx.save()
  ctx.shadowColor = nodeColor
  ctx.shadowBlur = lost ? 22 : 14 + upliftPx * 0.12
  ctx.fillStyle = nodeColor
  const nodeR = lost ? 4.5 : 4.5 + upliftPx * 0.03
  ctx.beginPath(); ctx.arc(contactX, headY, nodeR, 0, Math.PI * 2); ctx.fill()
  ctx.restore()

  // --- label + live force chip ---
  ctx.font = '600 13px Inter, system-ui, sans-serif'
  ctx.fillStyle = lost ? ARC : 'rgba(231,238,246,0.92)'
  ctx.fillText(label.toUpperCase(), 18, y0 + 26)
  ctx.font = '700 12px JetBrains Mono, ui-monospace, monospace'
  ctx.fillStyle = lost ? ARC : ACCENT
  const fval = sys ? `${sys.contact_force.toFixed(0)} N` : '—'
  ctx.fillText(fval, 18, y0 + 44)
  if (lost) {
    ctx.fillStyle = ARC
    ctx.fillText('CONTACT LOST', 70, y0 + 44)
  }

  // --- physics-proof overlays (toggleable) ---
  if (showPhysics && sys && frame) {
    drawForceArrows(ctx, contactX, headY, sys, frame, isAero, lost)
    drawEquationStrip(ctx, W, y0, H, sys, frame, lost)
  }
}

function drawTrain(ctx, contactX, railY, H) {
  const len = Math.min(360, H * 1.2)
  const x = contactX - len * 0.5
  const bodyH = H * 0.26
  const top = railY - bodyH - 6
  ctx.save()
  // body with long aerodynamic nose to the right
  ctx.beginPath()
  ctx.moveTo(x, top + bodyH)
  ctx.lineTo(x, top + 10)
  ctx.quadraticCurveTo(x, top, x + 14, top)
  ctx.lineTo(x + len - 70, top)
  ctx.quadraticCurveTo(x + len, top + 6, x + len, top + bodyH * 0.7) // nose
  ctx.quadraticCurveTo(x + len, top + bodyH, x + len - 16, top + bodyH)
  ctx.closePath()
  const grad = ctx.createLinearGradient(0, top, 0, top + bodyH)
  grad.addColorStop(0, '#1a2230')
  grad.addColorStop(1, '#0c111a')
  ctx.fillStyle = grad
  ctx.fill()
  ctx.strokeStyle = 'rgba(120,140,165,0.55)'
  ctx.lineWidth = 1.4
  ctx.stroke()
  // accent waistline
  ctx.strokeStyle = 'rgba(46,230,214,0.5)'
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(x + 6, top + bodyH * 0.62)
  ctx.lineTo(x + len - 24, top + bodyH * 0.62)
  ctx.stroke()
  // windows
  ctx.fillStyle = 'rgba(46,230,214,0.16)'
  for (let i = 0; i < 5; i++) {
    ctx.fillRect(x + 22 + i * 46, top + 12, 30, 16)
  }
  ctx.restore()
}

function drawPantograph(ctx, baseX, roofY, headY) {
  const half = 26
  ctx.save()
  ctx.strokeStyle = 'rgba(170,190,210,0.85)'
  ctx.lineWidth = 2.4
  ctx.lineJoin = 'round'
  // lower arms (wide base) -> knee
  const kneeY = (roofY + headY) / 2
  ctx.beginPath()
  ctx.moveTo(baseX - half, roofY)
  ctx.lineTo(baseX, kneeY)
  ctx.lineTo(baseX + half, roofY)
  ctx.stroke()
  // upper arms -> head
  ctx.beginPath()
  ctx.moveTo(baseX, kneeY)
  ctx.lineTo(baseX - 14, headY + 4)
  ctx.moveTo(baseX, kneeY)
  ctx.lineTo(baseX + 14, headY + 4)
  ctx.stroke()
  // collector head bar
  ctx.strokeStyle = 'rgba(200,215,230,0.95)'
  ctx.lineWidth = 3.2
  ctx.beginPath()
  ctx.moveTo(baseX - 20, headY + 2)
  ctx.lineTo(baseX + 20, headY + 2)
  ctx.stroke()
  ctx.restore()
}

function drawArc(ctx, x, headY, wireY, reduced) {
  ctx.save()
  ctx.strokeStyle = ARC
  ctx.shadowColor = ARC
  ctx.shadowBlur = 12
  ctx.lineWidth = 1.6
  const steps = 6
  ctx.beginPath()
  ctx.moveTo(x, headY)
  for (let i = 1; i < steps; i++) {
    const t = i / steps
    const jitter = reduced ? 0 : (Math.random() - 0.5) * 10
    ctx.lineTo(x + jitter, headY + (wireY - headY) * t)
  }
  ctx.lineTo(x, wireY)
  ctx.stroke()
  ctx.restore()
}

// ---------------- physics-proof overlays ----------------

function vArrow(ctx, x, yFrom, len, up, color, name, value) {
  const tip = up ? yFrom - len : yFrom + len
  const dir = up ? -1 : 1
  ctx.save()
  ctx.strokeStyle = color
  ctx.fillStyle = color
  ctx.lineWidth = 2
  ctx.beginPath(); ctx.moveTo(x, yFrom); ctx.lineTo(x, tip); ctx.stroke()
  ctx.beginPath() // arrowhead
  ctx.moveTo(x, tip)
  ctx.lineTo(x - 4, tip - dir * 7)
  ctx.lineTo(x + 4, tip - dir * 7)
  ctx.closePath(); ctx.fill()
  // label (name above value), placed beyond the tip
  ctx.font = `700 9.5px ${MONO}`
  ctx.textAlign = 'center'
  ctx.shadowColor = 'rgba(0,0,0,0.95)'
  ctx.shadowBlur = 4
  const ly = up ? tip - 12 : tip + 18
  ctx.fillText(name, x, ly - 6)
  ctx.fillText(value, x, ly + 4)
  ctx.restore()
}

// Free-body force arrows at the collector head, scaled to real newtons.
function drawForceArrows(ctx, cx, headY, sys, frame, isAero, lost) {
  const len = (n) => Math.min(Math.abs(n) * PX_PER_N, ARROW_MAX_PX)
  const P = lost ? 0 : (sys.contact_force ?? 0)
  const Fa = frame.aero_N ?? 0
  const F0 = frame.f0_N ?? 0
  const Fc = isAero ? (sys.f_control ?? 0) : 0
  const dim = 'rgba(180,198,216,0.92)'

  vArrow(ctx, cx - 42, headY, len(F0), true, dim, 'F₀', `${F0.toFixed(0)}`)
  vArrow(ctx, cx - 16, headY, len(Fa), true, dim, 'aero', `${Fa.toFixed(0)}`)
  if (isAero) {
    vArrow(ctx, cx + 16, headY, len(Fc), Fc >= 0, ACCENT, 'ctrl', `${Fc.toFixed(0)}`)
  }
  vArrow(ctx, cx + 42, headY, len(P), false, lost ? ARC : '#e7eef6', 'P', `${P.toFixed(0)}`)
}

// Live contact law including the coupled model's relative-velocity damping.
// Right-aligned to end clear of the top-right PHYSICS toggle (and the train).
function drawEquationStrip(ctx, W, y0, H, sys, frame, lost) {
  const z1 = sys.head_mm ?? 0
  const yw = sys.wire_mm ?? frame.wire_mm ?? 0
  const z1d = sys.head_velocity_mm_s ?? 0
  const ywd = sys.wire_velocity_mm_s ?? 0
  const P = sys.contact_force ?? 0
  const d = z1 - yw
  const elastic = 50 * d
  const dampingPerMm = (frame.contact_damping_N_s_m ?? 0) / 1000
  const damping = dampingPerMm * (z1d - ywd)
  const line1 = 'P = max[k_c·gap + c_c·relative velocity, 0]'
  const pre = lost
    ? `elastic ${elastic.toFixed(0)} N + damping ${damping.toFixed(0)} N → 0 N · SEPARATION`
    : `elastic ${elastic.toFixed(0)} N + damping ${damping.toFixed(0)} N = `
  const suf = lost ? '' : `${P.toFixed(0)} N ✓`

  ctx.save()
  ctx.textAlign = 'left'
  ctx.shadowColor = 'rgba(0,0,0,0.9)'
  ctx.shadowBlur = 4
  // measure with the fonts actually used
  ctx.font = `700 11px ${MONO}`
  const w1 = ctx.measureText(line1).width
  ctx.font = `700 11.5px ${MONO}`
  const wpre = ctx.measureText(pre).width
  const wsuf = suf ? ctx.measureText(suf).width : 0
  const maxW = Math.max(w1, wpre + wsuf)
  // block ends 128px from the right edge (clears the PHYSICS toggle); never left of mid-lane
  const x = Math.max(W - 128 - maxW, W * 0.46)

  ctx.font = `700 11px ${MONO}`
  ctx.fillStyle = 'rgba(150,166,184,0.95)'
  ctx.fillText(line1, x, y0 + 20)
  ctx.font = `700 11.5px ${MONO}`
  ctx.fillStyle = lost ? ARC : 'rgba(231,238,246,0.95)'
  ctx.fillText(pre, x, y0 + 37)
  if (suf) {
    ctx.fillStyle = ACCENT
    ctx.fillText(suf, x + wpre, y0 + 37)
  }
  ctx.restore()
}

// To-scale span dimension between two poles (horizontal is genuinely 1:1).
function drawSpanDimension(ctx, W, H, worldX) {
  const scroll = worldX % SPAN_PX
  // first pole comfortably right of the trains
  let p0 = -scroll
  while (p0 < W * 0.56) p0 += SPAN_PX
  const p1 = p0 + SPAN_PX
  if (p1 > W - 20) return
  const y = H - 34
  ctx.save()
  ctx.strokeStyle = 'rgba(150,166,184,0.6)'
  ctx.fillStyle = 'rgba(150,166,184,0.85)'
  ctx.lineWidth = 1
  ctx.beginPath(); ctx.moveTo(p0, y); ctx.lineTo(p1, y); ctx.stroke()
  for (const px of [p0, p1]) { ctx.beginPath(); ctx.moveTo(px, y - 5); ctx.lineTo(px, y + 5); ctx.stroke() }
  ctx.font = `700 10px ${MONO}`
  ctx.textAlign = 'center'
  ctx.shadowColor = 'rgba(0,0,0,0.9)'; ctx.shadowBlur = 4
  ctx.fillText('1 SPAN = 60 m', (p0 + p1) / 2, y - 8)
  ctx.restore()
}

// Provenance footer: what model produced this picture.
function drawModelCard(ctx, W, H, f) {
  const txt =
    `EN 50318 two-mass model  ·  k_c = 50 kN/m  ·  F₀ = ${(f.f0_N ?? 0).toFixed(0)} N  ·  ` +
    `RK4 + MODAL NEWMARK Δt = 1 ms  ·  shared exogenous seed, independent coupled wires  ·  vertical exaggerated`
  ctx.save()
  ctx.font = `600 10px ${MONO}`
  ctx.textAlign = 'center'
  ctx.fillStyle = 'rgba(129,144,163,0.6)'
  ctx.fillText(txt, W / 2, H - 12)
  ctx.restore()
}
