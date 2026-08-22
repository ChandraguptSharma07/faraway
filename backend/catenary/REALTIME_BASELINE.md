# Coupled real-time catenary baseline

The live dashboard now uses a lane-specific flexible wire. Contact force excites the
contact and messenger wires; their displacement and velocity feed back into the next
pantograph step. Passive, AeroPINN, idealized-reference, and controller-estimate wire
states are independent. They share only exogenous geometry, speed, tension setting,
and stochastic disturbance definitions.

## Reduction

- The existing distributed two-wire matrices remain the source model: tensioned
  Euler--Bernoulli contact/messenger wires, supports, and droppers.
- The lowest 36 mass-normalized modes are retained from an eight-span moving window.
- Average-acceleration Newmark advances the diagonal modal equations.
- A span is shifted out behind the pantograph and a zero-disturbance span enters ahead.
  Modal reprojection prevents a periodic wave from wrapping around forever.
- The contact is solved by an under-relaxed force/displacement iteration each 1 ms.
- Tension changes rebuild the modal basis and reproject existing displacement and
  velocity, changing stiffness/wave speed without resetting the wire to zero.
- Live droppers are linearized about the taut state. The asynchronous distributed
  shadow solver retains tension-only dropper switching.

This follows the published real-time strategy of projecting a finite-element
catenary into a truncated modal basis. The paper also warns that the truncation and
explicit interaction-force treatment require accuracy validation:
https://doi.org/10.1016/j.finel.2019.05.001

Wave propagation and dropper/support reflection are established features of the
pantograph-catenary problem:
https://doi.org/10.1016/j.apm.2018.01.001

The reference distributed-parameter formulation represents contact and messenger
wires as coupled tensioned beams with a moving load:
https://doi.org/10.1016/j.jsv.2017.08.008

## Control consequences

The controller cannot access the plant wire. A separate modal wire estimate is driven
by contact force reconstructed from the measured collector-head acceleration and EKF
state. Candidate MPC trajectories propagate their own estimated wire modes and penalize
wire displacement/velocity. Control authority is temporarily derated to ±25 N because
the full ±98.2 N simulated actuator excited the unidentified catenary modes. This limit
is simulation-tuned and must be replaced by rig identification.

The contact-force reconstruction assumes nominal speed-squared aerodynamic uplift.
Without a measured wind/load channel it cannot uniquely separate a sudden aerodynamic
gust from contact reaction; gust testing therefore remains a robustness test, not an
identified force estimate.

## Claim boundary

This is a higher-fidelity simulation, not a route-identified digital twin. The current
distributed shadow model is still marked `INVESTIGATE`; activating modal coupling does
not turn that disagreement into validation. Required next evidence includes modal-count
and window sensitivity, comparison with the implicit distributed solver, measured line
parameters, HIL timing, and EN 50318 validation after model identification.
