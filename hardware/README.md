# AeroPINN — Hardware servo loop (optional)

A single hobby servo that **twitches in sync with the AeroPINN control force**, so the
demo is visibly a real closed loop and not just a screen animation. In Round 1 the servo
controls nothing physical — it is a real-loop *indicator*.

> **The software demo runs fully without any hardware.** If no board is connected the
> backend silently disables the serial link and everything else works normally. The servo
> is purely additive and is never a dependency.

## What it does

1. The backend's control loop computes `F_control` (the counter-force AeroPINN applies).
2. `backend/server/servo.py` auto-detects a connected board and streams an angle
   (`F_control ∈ [−90, +90] N` → `0…180°`, centered at 90°) over USB serial at ~25 Hz.
3. The board (`aeropinn_servo/aeropinn_servo.ino`) reads the angle and drives the servo.

When AeroPINN works hard against a gust or beyond-envelope turbulence, the servo sweeps
visibly; when contact force is calm, it rests near center.

## Bill of materials

- 1 × ESP32 dev board **or** Arduino Uno/Nano
- 1 × hobby servo (SG90 micro for a quick demo; MG90S/standard for more visible throw)
- External 5 V supply for the servo if it is anything larger than an SG90
- Jumper wires

## Wiring

| Servo wire | Connect to |
|------------|------------|
| Signal (orange/white) | `SERVO_PIN` — **D9** on Uno/Nano, **GPIO13** on ESP32 |
| V+ (red) | 5 V (use an **external 5 V** supply for non-micro servos) |
| GND (brown/black) | Board GND **and** supply GND (common ground) |

> If using an external supply, tie its ground to the board ground. Do not power a standard
> servo from the board's onboard 5 V regulator under load.

## Flashing

**Arduino Uno/Nano** — uses the built-in `<Servo.h>`:
1. Open `aeropinn_servo/aeropinn_servo.ino` in the Arduino IDE.
2. Select the board + port, click Upload.

**ESP32** — install the **ESP32Servo** library (Library Manager), then in the sketch
replace `#include <Servo.h>` with `#include <ESP32Servo.h>` and set `SERVO_PIN = 13`.
The rest of the API is identical.

## Running with the servo

1. Flash the board and connect it via USB.
2. Start the backend as usual:
   `python -m uvicorn backend.server.app:app --port 8000`
3. The link auto-detects the port. To force a specific port:
   `AEROPINN_SERIAL_PORT=COM5 python -m uvicorn backend.server.app:app --port 8000`
   (Windows: `COM5`; Linux: `/dev/ttyUSB0`; macOS: `/dev/cu.usbserial-XXXX`.)
4. `GET /health` reports `{"servo_connected": true, "port": "COM5"}` when linked.

## No-hardware fallback (verified)

With no board attached, `/health` reports `"servo_connected": false` and the full
software demo (simulation, PINN, controller, UI, credibility view) runs unchanged.
