# Pneumatic frame-actuator baseline

Status: **datasheet baseline; not identified on hardware; not railway qualified**.

## Selected test-rig components

- Valve: SMC VER2000 5-port electro-pneumatic proportional valve.
- Cylinder: SMC MQQ/MQM 25 mm low-friction, double-acting cylinder.
- Mounting: parallel to the pantograph raising mechanism, applying force to the
  articulated frame—not the collector head.

This layout follows the experimentally tested RTRI active-pantograph architecture.
The commercial parts are a reproducible laboratory baseline; they are not claimed
to be the proprietary RTRI actuator or approved for roof-mounted railway service.

## Model parameters

| Parameter | Model value | Basis |
|---|---:|---|
| Valve response | 40 ms | VER2000 published response time |
| First-order time constant | 40 ms | Conservative model interpretation of response time |
| Digital transport delay | 4 ms | Assumption; must be measured end-to-end |
| Piston cap-side area | 490.9 mm² | MQQ/MQM 25 mm manufacturer table |
| Differential-pressure cap | 0.2 MPa | Selected safe test-rig operating point |
| Force cap | 98.2 N | `490.9 mm² × 0.2 MPa` |
| Force-rate cap | 2455 N/s | `98.2 N / 0.040 s`; derived, not measured |

## Required identification test

Before hardware deployment:

1. Install an inline load cell between cylinder and frame.
2. Log command, both chamber pressures, force, rod displacement and timestamps at
   1 kHz or faster.
3. Apply safe positive/negative steps and swept-sine commands across multiple
   amplitudes.
4. Estimate dead time, rise/fall dynamics, force saturation, slew rate, hysteresis,
   friction and pressure dependence.
5. Repeat across supply pressure and expected temperature range.
6. Replace the assumed/derived parameters in `actuator.py`, retrain if the force
   channel changes, and rerun `python -m backend.controller.robustness`.

Do not change `DATASHEET_BASELINE_NOT_IDENTIFIED` to an identified or deployable
status until this test has been completed.

## Primary sources

- [RTRI active pantograph study](https://doi.org/10.2219/rtriqr.53.28)
- [SMC VER2000/4000 datasheet](https://www.smcworld.com/catalog/BEST-5-5-en/mpv/5-p0892-0898-ver_en/data/5-p0892-0898-ver_en.pdf)
- [SMC MQQ/MQM/MQP datasheet](https://www.smcworld.com/catalog/en/actuator/MQQ-MQM-MQP-E/6-2-3-p0317-0344-mq_en/data/6-2-3-p0317-0344-mq_en.pdf)
