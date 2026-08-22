/*
 * AeroPINN — servo loop (Round 1: prove the loop is real)
 *
 * Reads newline-terminated servo-angle integers (0..180) from USB serial at
 * 115200 baud and drives a hobby servo to that angle. The backend sends the
 * AeroPINN control force F_control mapped to an angle, so the servo physically
 * twitches in sync with the controller — making the closed loop visible on camera.
 *
 * The servo controls nothing physical yet; it is a real-loop indicator only.
 *
 * Boards:
 *   - Arduino Uno/Nano: uses the built-in <Servo.h>. Signal on pin 9.
 *   - ESP32: install the "ESP32Servo" library and replace <Servo.h> with
 *     <ESP32Servo.h>; SERVO_PIN 13 works well. (API is identical.)
 *
 * Wiring (see hardware/README.md): servo signal -> SERVO_PIN, servo V+ -> 5V
 * (external 5V supply recommended for anything but a micro servo), GND common.
 */

#include <Servo.h>

const int  SERVO_PIN = 9;
const long BAUD       = 115200;

Servo servo;
int   target = 90;   // commanded angle from serial
float current = 90;  // smoothed angle actually written
String buf;

void setup() {
  Serial.begin(BAUD);
  servo.attach(SERVO_PIN);
  servo.write(90);   // centered = zero control force
}

void applyLine(String s) {
  s.trim();
  if (s.length() == 0) return;
  int a = s.toInt();
  if (a < 0) a = 0;
  if (a > 180) a = 180;
  target = a;
}

void loop() {
  // parse all complete lines currently available
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      applyLine(buf);
      buf = "";
    } else {
      buf += c;
      if (buf.length() > 8) buf = "";  // guard against garbage
    }
  }

  // light smoothing so the motion reads cleanly on camera (~exponential)
  current += (target - current) * 0.35;
  servo.write((int)round(current));
  delay(15);  // ~66 Hz update
}
