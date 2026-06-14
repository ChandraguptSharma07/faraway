"""Optional servo link — proves the control loop is physically real.

The backend streams the AeroPINN control force over serial; an ESP32/Arduino maps
it to a servo angle so the servo twitches in sync with F_control on camera.

CRITICAL: this is purely additive. If no board is connected (no serial port, or
pyserial missing, or any write error) the link silently disables itself and the
entire software demo runs normally. Hardware is never a dependency.

Force -> angle map: F_control in [-F_MAX, +F_MAX] N -> [0, 180] deg, centered at 90.
Set AEROPINN_SERIAL_PORT to force a port; otherwise we auto-detect a likely board.
"""

from __future__ import annotations

import os
import time

F_MAX = 90.0
BAUD = 115200
MIN_INTERVAL = 0.04  # s  ~25 Hz serial cadence (don't flood the link)

# USB vendor IDs commonly seen on ESP32 / Arduino dev boards.
_LIKELY_VIDS = {0x10C4, 0x1A86, 0x0403, 0x2341, 0x303A}


class ServoLink:
    def __init__(self) -> None:
        self.enabled = False
        self._ser = None
        self._last = 0.0
        self.port = None
        self._connect()

    def _find_port(self):
        forced = os.environ.get("AEROPINN_SERIAL_PORT")
        if forced:
            return forced
        try:
            from serial.tools import list_ports
        except Exception:
            return None
        # Only auto-claim a port that looks like an Arduino/ESP32 board. We do NOT
        # grab an arbitrary first COM port (it could be Bluetooth or another device);
        # an unrecognized board can always be selected with AEROPINN_SERIAL_PORT.
        for p in list_ports.comports():
            if p.vid in _LIKELY_VIDS:
                return p.device
        return None

    def _connect(self) -> None:
        try:
            import serial  # pyserial
        except Exception:
            return
        port = self._find_port()
        if not port:
            return  # no board -> stay disabled, app runs normally
        try:
            self._ser = serial.Serial(port, BAUD, timeout=0, write_timeout=0)
            self.port = port
            self.enabled = True
        except Exception:
            self._ser = None  # port busy / permission -> disabled

    def send(self, f_control: float) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        if now - self._last < MIN_INTERVAL:
            return
        self._last = now
        angle = int(round(90 + 90 * max(-1.0, min(1.0, f_control / F_MAX))))
        try:
            self._ser.write(f"{angle}\n".encode())
        except Exception:
            # any failure -> disable and keep the software demo running
            self.enabled = False
            try:
                self._ser.close()
            except Exception:
                pass

    def status(self) -> dict:
        return {"servo_connected": self.enabled, "port": self.port}

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
        self.enabled = False
