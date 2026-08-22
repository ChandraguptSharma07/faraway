# Sensor and state-estimation baseline

This is a simulation baseline for a future instrumented rig, not an identified or
railway-qualified sensing system. The live controller receives no simulator state.
It receives only delayed, sampled, noisy and quantised measurements through
`MeasurementChain`; `PantographEKF` estimates `[z1, z1_dot, z2, z2_dot]`.

## Proposed channels

- Two miniature LVDT-class channels: articulated-frame position and collector-head
  travel relative to the frame. TE's miniature LVDT family publishes ±0.25% of full
  range linearity. The simulation assumes startup zeroing leaves 0.02 mm RMS bias.
- Two PCB 353B34-class accelerometers on the head and frame. Its datasheet publishes
  0.005 m/s² broadband resolution and a 1–4000 Hz ±5% band. The simulation uses
  0.01 m/s² random noise plus 0.005 m/s² residual post-calibration bias.
- Cylinder pressure converted to force. The SMC PSE300-class controller publishes
  1 ms response and 1/1000 display resolution. The simulated 98.2 N range therefore
  uses 0.1 N quantisation, 0.2 N random noise and 0.05 N residual bias.

## Explicit assumptions

- 500 Hz acquisition, 2 ms end-to-end delivery latency, and 0.1% packet dropout.
- A packet older than 20 ms removes active force and leaves passive pantograph
  behavior. This is a simulation fail-safe, not a certified safety function.
- Delayed updates currently inflate measurement covariance. Hardware work should
  replace this with timestamped fixed-lag replay after timing is measured.
- Simulator truth remains in the server only for validation metrics and the labeled
  idealized reference. It is not an input to the deployable control path.
- The EKF and MPC receive a deterministic catenary prior. They cannot query simulated
  random turbulence, transient gusts, or their future values.

## Manufacturer references

- PCB 353B34 accelerometer: https://www.pcb.com/contentStore/docs/pcb_corporate/vibration/products/specsheets/353b34_p.pdf
- TE miniature LVDT family: https://www.te.com/en/product-CAT-LVDT0021.html
- SMC PSE300 controller: https://www.smcworld.com/webcatalog/en-jp/series/PSE300-S-E
