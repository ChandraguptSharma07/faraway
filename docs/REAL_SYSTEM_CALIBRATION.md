# Real-system calibration contract

## Current claim boundary

AeroPINN is a research simulation with EN 50318 reference-range checks. It is not
yet a route-identified digital twin, hardware validation, railway certification, or
safety function. The Lastochka GLB supplies visual geometry only. No CHS2 or
Lastochka measurement dataset is present in this repository, so train-specific
physical parameters must not be inferred from the mesh.

The next milestone is an identified baseline dataset. Model complexity should only
increase after the corresponding variables are measurable; otherwise additional
equations add untestable assumptions rather than fidelity.

## Required inputs

All signals need units, coordinate/sign convention, sensor model and calibration
date, sampling rate, timestamps, uncertainty, and missing-data flags.

### Pantograph

- Exact pantograph and collector-head model, geometry, mounting location, and static
  uplift setting.
- Lumped masses/inertias, link geometry, stiffness and damping, joint friction,
  bump stops, and carbon-strip properties/wear.
- Vertical displacement, velocity or acceleration at the head and frame.
- Aerodynamic lift/drag coefficients versus speed, yaw, pantograph height, and train
  orientation. Wind-tunnel or controlled coast-down/line-test provenance is needed.

### Catenary and route

- Route/track identifier and surveyed chainage; span length and stagger per span.
- Contact and messenger wire mass, tension, bending stiffness, damping, and material.
- Dropper position, length, stiffness, preload, and slack state; steady-arm and
  support stiffness; registration geometry and boundary conditions.
- Tensioning equipment state, wire wear, installation tolerances, maintenance events,
  ambient/wire temperature, ice or contamination observations.

### Actuator and sensing

- Command-to-force curves in both directions, saturation, rate limit, hysteresis,
  deadband, transport delay, bandwidth, temperature dependence, and failure state.
- Contact-force reference sensor, accelerometers, position sensors, wind sensors,
  train speed/position, command and applied-force feedback on one synchronized clock.
- Raw data plus calibration certificates/uncertainty—not only filtered dashboard
  exports.

### Dynamic runs

- Repeated passive and controlled traversals over the same instrumented spans at
  multiple speeds, directions, temperatures, and wind conditions.
- Contact force, head/frame motion, command/applied force, speed, chainage, tension,
  wire uplift where available, arc/contact-loss events, and weather.
- Startup and braking sections identified separately from steady-speed evaluation.

## Dataset split

Partition by complete run and operating condition, never by random adjacent samples:

- Calibration: identify plant, sensor, actuator, aerodynamic, and disturbance
  parameters.
- Tuning: choose model order and controller weights without touching final gates.
- Blind validation: held by another team member; includes unseen spans, days,
  directions, speeds, temperature and wind.

Record dataset hashes, code commit, parameter file, random seeds, preprocessing, and
excluded intervals for every report. Never tune against the blind set after opening
it; failed blind evidence starts a new version and requires a new blind set.

## Acceptance ladder

1. Data integrity: clock alignment and units verified; dropout/outlier policy frozen;
   force and motion sensors have uncertainty budgets.
2. Component identification: passive pantograph, catenary, actuator, sensors, and
   aerodynamic load each match dedicated tests with residuals reported by condition.
3. Numerical adequacy: timestep, mesh, window and modal-order sensitivity pass before
   model-to-measurement scoring.
4. Passive blind validation: mean force, standard deviation, spectrum/coherence,
   contact loss, uplift and transient peaks pass predeclared tolerances.
5. Controlled blind validation: compare paired runs and report confidence intervals,
   actuator constraints, deadline misses, estimator failures and worst-case runs.
6. Hardware-in-the-loop: real controller target, I/O and actuator emulator under
   delay, dropout, saturation, gust, temperature and safe-failure tests.
7. Supervised route trial and applicable railway assurance process. Simulation gates
   do not replace approval by the infrastructure/operator and safety authorities.

Exact numeric tolerances for steps 2, 4, and 5 must be agreed with the dataset owner
and domain engineer before calibration begins. The software must not invent them.

## Recommended delivery format

Use one immutable metadata file per run plus columnar telemetry (CSV is acceptable for
the first exchange; Parquet/HDF5 is preferable at scale). Include a data dictionary,
route redaction policy, and a small representative sample before transferring the full
dataset. The first implementation task after receipt is a schema validator and time
alignment report—not PINN retraining.
