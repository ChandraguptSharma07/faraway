import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { useThrottledFrame } from '../hooks/useTelemetry'

const TRAIN_URL = '/models/lastochka.glb'
const ACCENT = 0x2ee6d6
const PASSIVE = 0xd1a84b
const ARC = 0xff3b3b
const Y_AXIS = new THREE.Vector3(0, 1, 0)
const PANTOGRAPH_X = -6.4
const PANTOGRAPH_Y = -0.42
const MILLIMETRES_TO_SCENE = 0.001

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value))
}

function setRod(mesh, a, b) {
  const direction = new THREE.Vector3().subVectors(b, a)
  const length = direction.length()
  mesh.position.copy(a).add(b).multiplyScalar(0.5)
  mesh.scale.set(1, length, 1)
  mesh.quaternion.setFromUnitVectors(Y_AXIS, direction.normalize())
}

function makeRod(material, radius = 0.045) {
  return new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, 1, 10),
    material,
  )
}

function makePantograph(isActive) {
  const group = new THREE.Group()
  group.name = isActive ? 'AeroPINN_pantograph' : 'passive_pantograph'

  const metal = new THREE.MeshStandardMaterial({
    color: 0xb7c1cc,
    metalness: 0.75,
    roughness: 0.28,
  })
  const dark = new THREE.MeshStandardMaterial({
    color: 0x252d37,
    metalness: 0.65,
    roughness: 0.4,
  })
  const ceramic = new THREE.MeshStandardMaterial({
    color: 0xa85e45,
    metalness: 0.05,
    roughness: 0.58,
  })
  const actuator = new THREE.MeshStandardMaterial({
    color: isActive ? ACCENT : 0x596574,
    emissive: isActive ? ACCENT : 0x000000,
    emissiveIntensity: isActive ? 0.55 : 0,
    metalness: 0.5,
    roughness: 0.3,
  })

  const mountingPlate = new THREE.Mesh(
    new THREE.BoxGeometry(1.55, 0.1, 1.05),
    dark,
  )
  mountingPlate.position.y = 1.76
  group.add(mountingPlate)

  const rods = []
  for (let i = 0; i < 8; i += 1) {
    const rod = makeRod(metal)
    rods.push(rod)
    group.add(rod)
  }

  const crossbars = [makeRod(dark, 0.055), makeRod(dark, 0.05)]
  group.add(...crossbars)

  const drive = makeRod(actuator, 0.075)
  group.add(drive)

  const collector = new THREE.Mesh(
    new THREE.BoxGeometry(0.14, 0.075, 2.05),
    new THREE.MeshStandardMaterial({
      color: 0x252a31,
      metalness: 0.35,
      roughness: 0.72,
    }),
  )
  group.add(collector)

  const contact = new THREE.Mesh(
    new THREE.SphereGeometry(0.085, 14, 10),
    new THREE.MeshStandardMaterial({
      color: isActive ? ACCENT : PASSIVE,
      emissive: isActive ? ACCENT : PASSIVE,
      emissiveIntensity: 1.4,
    }),
  )
  group.add(contact)

  for (const x of [-0.58, 0.58]) {
    for (const z of [-0.36, 0.36]) {
      const insulator = new THREE.Mesh(
        new THREE.CylinderGeometry(0.12, 0.15, 0.22, 12),
        ceramic,
      )
      insulator.position.set(x, 1.93, z)
      group.add(insulator)
    }
  }

  const arrows = new THREE.Group()
  const makeArrow = (color, x) => {
    const arrow = new THREE.ArrowHelper(Y_AXIS, new THREE.Vector3(x, 3, 0), 0.6, color, 0.18, 0.1)
    arrows.add(arrow)
    return arrow
  }
  const forceArrows = {
    staticForce: makeArrow(0xd7e0e9, -0.72),
    aero: makeArrow(0x8fa1b5, -0.28),
    control: makeArrow(ACCENT, 0.28),
    contact: makeArrow(0xffffff, 0.72),
  }
  group.add(arrows)

  const arcGeometry = new THREE.BufferGeometry()
  arcGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(15), 3))
  const arc = new THREE.Line(
    arcGeometry,
    new THREE.LineBasicMaterial({ color: ARC, transparent: true, opacity: 0.95 }),
  )
  group.add(arc)

  return {
    group,
    update(system, frame, showPhysics, reduced, motionGain) {
      const headMm = system?.head_mm ?? 0
      const wireMm = system?.wire_mm ?? frame?.wire_mm ?? 0
      const lost = system?.contact_lost ?? false
      const frameMm = system?.frame_mm ?? 0
      const baseY = 2.0
      const scenePerMm = MILLIMETRES_TO_SCENE * motionGain
      let topY = 3.25 + clamp(headMm, -100, 100) * scenePerMm
      const wireY = 3.25 + clamp(wireMm, -100, 100) * scenePerMm
      const visibleContactGap = 2 * scenePerMm
      if (lost && topY > wireY - visibleContactGap) {
        topY = wireY - visibleContactGap
      }
      topY = clamp(topY, baseY + 0.5, baseY + 2.5)
      const midY = baseY + (topY - baseY) * 0.52 + clamp(frameMm, -100, 100) * scenePerMm

      const sides = [-0.34, 0.34]
      let index = 0
      for (const z of sides) {
        const baseLeft = new THREE.Vector3(-0.62, baseY, z)
        const baseRight = new THREE.Vector3(0.62, baseY, z)
        const midLeft = new THREE.Vector3(0.34, midY, z)
        const midRight = new THREE.Vector3(-0.34, midY, z)
        const topLeft = new THREE.Vector3(-0.3, topY - 0.08, z)
        const topRight = new THREE.Vector3(0.3, topY - 0.08, z)
        setRod(rods[index++], baseLeft, midLeft)
        setRod(rods[index++], midLeft, topRight)
        setRod(rods[index++], baseRight, midRight)
        setRod(rods[index++], midRight, topLeft)
      }

      setRod(crossbars[0], new THREE.Vector3(-0.62, baseY, -0.42), new THREE.Vector3(-0.62, baseY, 0.42))
      setRod(crossbars[1], new THREE.Vector3(0, topY - 0.08, -0.48), new THREE.Vector3(0, topY - 0.08, 0.48))
      setRod(drive, new THREE.Vector3(0.58, baseY + 0.04, 0), new THREE.Vector3(-0.28, midY, 0))

      collector.position.set(0, topY, 0)
      contact.position.set(0, topY + 0.06, 0)
      contact.material.color.setHex(lost ? ARC : (isActive ? ACCENT : PASSIVE))
      contact.material.emissive.setHex(lost ? ARC : (isActive ? ACCENT : PASSIVE))

      arrows.visible = showPhysics
      const f0 = frame?.f0_N ?? 0
      const fa = frame?.aero_N ?? 0
      const fc = isActive ? (system?.f_control ?? 0) : 0
      const pressure = lost ? 0 : (system?.contact_force ?? 0)
      const arrowData = [
        [forceArrows.staticForce, f0, 1],
        [forceArrows.aero, fa, 1],
        [forceArrows.control, Math.abs(fc), fc >= 0 ? 1 : -1],
        [forceArrows.contact, pressure, -1],
      ]
      for (const [arrow, force, sign] of arrowData) {
        arrow.visible = force > 0.5
        arrow.position.y = topY + (sign > 0 ? 0.14 : -0.05)
        arrow.setDirection(new THREE.Vector3(0, sign, 0))
        arrow.setLength(clamp(force * 0.006, 0.18, 0.9), 0.16, 0.09)
      }

      arc.visible = lost
      if (lost) {
        const positions = arc.geometry.attributes.position.array
        const gapTop = Math.max(wireY, topY + visibleContactGap)
        for (let i = 0; i < 5; i += 1) {
          const k = i / 4
          positions[i * 3] = (i === 0 || i === 4 || reduced) ? 0 : (Math.random() - 0.5) * 0.18
          positions[i * 3 + 1] = topY + 0.08 + (gapTop - topY - 0.08) * k
          positions[i * 3 + 2] = reduced ? 0 : (Math.random() - 0.5) * 0.1
        }
        arc.geometry.attributes.position.needsUpdate = true
      }
      return { topY, wireY, lost }
    },
  }
}

function makeWire(laneZ) {
  const count = 33
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3))
  const line = new THREE.Line(
    geometry,
    new THREE.LineBasicMaterial({ color: 0xa9b7c6, transparent: true, opacity: 0.72 }),
  )
  line.position.z = laneZ

  const messengerGeometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-26, 4.45, laneZ),
    new THREE.Vector3(26, 4.45, laneZ),
  ])
  const messenger = new THREE.Line(
    messengerGeometry,
    new THREE.LineBasicMaterial({ color: 0x617286, transparent: true, opacity: 0.42 }),
  )

  return {
    line,
    messenger,
    update(contactX, baseY, contactY, lost) {
      const positions = geometry.attributes.position.array
      for (let i = 0; i < count; i += 1) {
        const x = -26 + (52 * i) / (count - 1)
        const normalizedDistance = (x - contactX) / 2.1
        const influence = Math.exp(-(normalizedDistance ** 2))
        positions[i * 3] = x
        positions[i * 3 + 1] = baseY * (1 - influence) + contactY * influence
        positions[i * 3 + 2] = 0
      }
      geometry.attributes.position.needsUpdate = true
      line.material.color.setHex(lost ? ARC : 0xa9b7c6)
      messenger.position.y = baseY - 3.25
    },
  }
}

function makeTrack(laneZ) {
  const group = new THREE.Group()
  const railMaterial = new THREE.MeshStandardMaterial({ color: 0x59626d, metalness: 0.8, roughness: 0.35 })
  const sleeperMaterial = new THREE.MeshStandardMaterial({ color: 0x272c33, roughness: 0.82 })
  const railGeometry = new THREE.BoxGeometry(52, 0.09, 0.1)
  for (const z of [-0.78, 0.78]) {
    const rail = new THREE.Mesh(railGeometry, railMaterial)
    rail.position.set(0, -2.2, laneZ + z)
    group.add(rail)
  }

  const sleeperGeometry = new THREE.BoxGeometry(0.18, 0.09, 2.15)
  const sleepers = new THREE.InstancedMesh(sleeperGeometry, sleeperMaterial, 45)
  group.add(sleepers)
  const matrix = new THREE.Matrix4()
  return {
    group,
    update(offset) {
      for (let i = 0; i < 45; i += 1) {
        // Lastochka's cab points toward -X, so the ground must travel +X.
        matrix.makeTranslation(-26 + i * 1.2 + offset, -2.27, laneZ)
        sleepers.setMatrixAt(i, matrix)
      }
      sleepers.instanceMatrix.needsUpdate = true
    },
  }
}

function keepLeadCar(scene) {
  const root = scene.getObjectByName('RootNode')
  if (!root) return
  const toRemove = []
  for (const child of root.children) {
    if (child.name !== 'kuz') toRemove.push(child)
  }
  for (const child of toRemove) {
    child.removeFromParent()
  }
}

function makeLane(source, laneZ, isActive) {
  const root = new THREE.Group()
  root.position.z = laneZ

  const train = source.clone(true)
  keepLeadCar(train)
  train.position.x = -7.4
  root.add(train)

  const pantograph = makePantograph(isActive)
  pantograph.group.position.set(PANTOGRAPH_X, PANTOGRAPH_Y, 0)
  root.add(pantograph.group)

  const underglow = new THREE.PointLight(isActive ? ACCENT : PASSIVE, 5, 8, 2)
  underglow.position.set(0, -1.5, 0)
  root.add(underglow)

  return { root, pantograph }
}

export default function World3D({
  frameRef,
  prefersReducedMotion,
  showPhysics = true,
  motionGain = 1,
  cameraReset = 0,
}) {
  const mountRef = useRef(null)
  const controlsRef = useRef(null)
  const reducedRef = useRef(prefersReducedMotion)
  const physicsRef = useRef(showPhysics)
  const motionGainRef = useRef(motionGain)
  const frame = useThrottledFrame(frameRef, 10)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    reducedRef.current = prefersReducedMotion
  }, [prefersReducedMotion])

  useEffect(() => {
    physicsRef.current = showPhysics
  }, [showPhysics])

  useEffect(() => {
    motionGainRef.current = motionGain
  }, [motionGain])

  useEffect(() => {
    if (cameraReset > 0) controlsRef.current?.reset()
  }, [cameraReset])

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return undefined

    let alive = true
    let raf = 0
    const scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x05070b, 0.025)

    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 120)
    camera.position.set(-20, 8.8, 18.5)
    camera.lookAt(0, 0.1, 0)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    renderer.setPixelRatio(1)
    renderer.setClearColor(0x05070b, 0)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.3
    mount.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(0, 0.1, 0)
    controls.enableDamping = !reducedRef.current
    controls.dampingFactor = 0.07
    controls.enablePan = true
    controls.screenSpacePanning = false
    controls.minDistance = 9
    controls.maxDistance = 48
    controls.minPolarAngle = 0.2
    controls.maxPolarAngle = Math.PI * 0.49
    controls.zoomSpeed = 0.8
    controls.panSpeed = 0.65
    controls.rotateSpeed = 0.55
    controls.update()
    controls.saveState()
    controlsRef.current = controls

    const resetCamera = () => controls.reset()
    renderer.domElement.addEventListener('dblclick', resetCamera)

    scene.add(new THREE.HemisphereLight(0xd8ecff, 0x1b2029, 3.0))
    const key = new THREE.DirectionalLight(0xffffff, 4.4)
    key.position.set(-8, 14, 10)
    scene.add(key)
    const rim = new THREE.DirectionalLight(ACCENT, 2.6)
    rim.position.set(12, 7, -10)
    scene.add(rim)

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(70, 30),
      new THREE.MeshStandardMaterial({ color: 0x080b10, roughness: 0.94, metalness: 0.08 }),
    )
    floor.rotation.x = -Math.PI / 2
    floor.position.y = -2.34
    scene.add(floor)

    const laneData = []
    const tracks = [makeTrack(-3.7), makeTrack(3.7)]
    for (const track of tracks) scene.add(track.group)
    const wires = [makeWire(-3.7), makeWire(3.7)]
    for (const wire of wires) scene.add(wire.line, wire.messenger)

    const resize = () => {
      const rect = mount.getBoundingClientRect()
      renderer.setSize(rect.width, rect.height, false)
      camera.aspect = rect.width / Math.max(rect.height, 1)
      camera.updateProjectionMatrix()
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(mount)

    new GLTFLoader().load(
      TRAIN_URL,
      (gltf) => {
        if (!alive) return
        const passive = makeLane(gltf.scene, -3.7, false)
        const active = makeLane(gltf.scene, 3.7, true)
        laneData.push(passive, active)
        scene.add(passive.root, active.root)
        setLoading(false)
      },
      undefined,
      (loadError) => {
        if (!alive) return
        setError(loadError?.message || '3D model failed to load')
        setLoading(false)
      },
    )

    const clock = new THREE.Clock()
    const draw = () => {
      const elapsed = clock.getElapsedTime()
      const current = frameRef.current
      const systems = [current?.passive, current?.aeropinn]
      const trackOffset = current ? ((current.speed_kmh / 3.6) * elapsed * 0.06) % 1.2 : 0

      for (let i = 0; i < tracks.length; i += 1) tracks[i].update(trackOffset)
      for (let i = 0; i < laneData.length; i += 1) {
        const result = laneData[i].pantograph.update(
          systems[i],
          current,
          physicsRef.current,
          reducedRef.current,
          motionGainRef.current,
        )
        const contactX = PANTOGRAPH_X
        const contactY = result.lost ? result.wireY : result.topY + 0.065
        wires[i].update(contactX, result.wireY, contactY, result.lost)
      }

      controls.enableDamping = !reducedRef.current
      controls.update()
      renderer.render(scene, camera)
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)

    return () => {
      alive = false
      cancelAnimationFrame(raf)
      observer.disconnect()
      renderer.domElement.removeEventListener('dblclick', resetCamera)
      controls.dispose()
      controlsRef.current = null
      scene.traverse((object) => {
        if (object.geometry) object.geometry.dispose()
        if (object.material) {
          const materials = Array.isArray(object.material) ? object.material : [object.material]
          for (const material of materials) material.dispose()
        }
      })
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [frameRef])

  const passive = frame?.passive
  const active = frame?.aeropinn

  return (
    <div className="world3d" ref={mountRef}>
      {(loading || error) && (
        <div className={`world3d-status mono ${error ? 'error' : ''}`}>
          {error || 'loading Lastochka digital twin…'}
        </div>
      )}
      <LaneHud label="PASSIVE" system={passive} side="left" />
      <LaneHud label="AeroPINN" system={active} side="right" active />
      {motionGain > 1 && (
        <div className="motion-scale mono">
          MOTION AMPLIFIED ×{motionGain} · METRICS UNSCALED
        </div>
      )}
      <div className="world3d-nav-hint mono">
        DRAG ORBIT · WHEEL ZOOM · RIGHT-DRAG PAN · DOUBLE-CLICK RESET
      </div>
      <div className="model-credit">
        Lastochka model by tiunov.se · CC BY 4.0 · modified for AeroPINN
      </div>
    </div>
  )
}

function LaneHud({ label, system, side, active }) {
  const lost = system?.contact_lost
  return (
    <div className={`lane-hud ${side} ${active ? 'active' : ''} ${lost ? 'lost' : ''}`}>
      <div className="lane-hud-title">{label}</div>
      <div className="lane-hud-value mono">
        {system ? system.contact_force.toFixed(0) : '—'}<small> N</small>
      </div>
      <div className="lane-hud-state">{lost ? 'CONTACT LOST · ARC' : 'CONTACT HELD'}</div>
    </div>
  )
}
