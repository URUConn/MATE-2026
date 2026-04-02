#include <Wire.h>

#define MUX_ADDR 0x70
#define AS5600_ADDR 0x36
const uint8_t SENSOR_AXES = 5;  // J1..J5 from AS5600 sensors
const uint8_t OUTPUT_AXES = 7;  // J1..J7 published to ROS bridge
const uint8_t JOYSTICK_AXES = 2;

const uint8_t JOYSTICK_PINS[JOYSTICK_AXES] = {A0, A1};
const int JOYSTICK_DIRECTION[JOYSTICK_AXES] = {1, 1};
const float JOYSTICK_DEADBAND = 0.06;

// Physical joint limits (deg) for J1..J5.
const float JOINT_MAX_DEG[SENSOR_AXES] = {165.0, 119.0, 119.0, 270.0, 270.0};

// Active encoder span (deg) used to control each joint. Remaining span is deadzone.
// Setting this equal to joint max gives a 1:1 "encoder angle == joint angle" feel.
const float ENCODER_ACTIVE_DEG[SENSOR_AXES] = {165.0, 119.0, 119.0, 270.0, 270.0};

// Zero offsets (degrees)
float zeroOffset[SENSOR_AXES] = {
  0, 0, 0, 0, 0
};

// Direction (1 or -1)
int direction[SENSOR_AXES] = {1, 1, 1, 1, 1};

// Calibration values (degrees after offset is applied).
// Must be in increasing physical order: 0 -> 90 -> 180 -> 270.
float calDeg[SENSOR_AXES][4] = {
  {0, 90, 180, 270},
  {0, 90, 180, 270},
  {0, 90, 180, 270},
  {0, 90, 180, 270},
  {0, 90, 180, 270}
};

// Clamp is enforced on onboard arm_servo_node; Arduino publishes calibrated angles only.

void selectMuxChannel(uint8_t ch) {
  Wire.beginTransmission(MUX_ADDR);
  Wire.write(1 << ch);
  Wire.endTransmission();
}

uint16_t readRawAngle() {
  Wire.beginTransmission(AS5600_ADDR);
  Wire.write(0x0C);
  Wire.endTransmission(false);
  Wire.requestFrom(AS5600_ADDR, 2);
  return (Wire.read() << 8) | Wire.read();
}

float wrapAngle(float a) {
  while (a < 0) a += 360;
  while (a >= 360) a -= 360;
  return a;
}

// Simple calibration
float applyCalibration(float angle, int ch) {
  float a0 = calDeg[ch][0];
  float a90 = calDeg[ch][1];
  float a180 = calDeg[ch][2];
  float a270 = calDeg[ch][3];

  float a = angle;
  if (a < a0) a += 360;

  if (a < a90) {
    return (a - a0) / (a90 - a0) * 90.0;
  } else if (a < a180) {
    return 90.0 + (a - a90) / (a180 - a90) * 90.0;
  } else if (a < a270) {
    return 180.0 + (a - a180) / (a270 - a180) * 90.0;
  } else {
    return 270.0 + (a - a270) / ((a0 + 360) - a270) * 90.0;
  }
}

float encoderToJointDeg(int ch, float encoderDeg) {
  // Map only the active encoder span to joint range.
  // The remaining span is a deadzone, and the 0<->max snap is placed at the
  // middle of that deadzone (instead of at the 0/360 wrap boundary).
  float activeDeg = ENCODER_ACTIVE_DEG[ch];
  float jointMax = JOINT_MAX_DEG[ch];
  if (activeDeg <= 0.0) {
    return 0.0;
  }

  if (activeDeg >= 360.0) {
    return encoderDeg * (jointMax / 360.0);
  }

  float deadzoneDeg = 360.0 - activeDeg;
  float deadzoneMid = activeDeg + (deadzoneDeg * 0.5);

  if (encoderDeg <= activeDeg) {
    return encoderDeg * (jointMax / activeDeg);
  }

  // First half of deadzone holds max, second half holds 0.
  // This makes the discontinuity happen at deadzone center.
  if (encoderDeg <= deadzoneMid) {
    return jointMax;
  }

  return 0.0;
}

float clampValue(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

float readJoystickNormalized(uint8_t index) {
  int raw = analogRead(JOYSTICK_PINS[index]);
  float normalized = (float(raw) - 512.0) / 512.0;
  normalized = clampValue(normalized, -1.0, 1.0);
  normalized *= JOYSTICK_DIRECTION[index];
  if (normalized > -JOYSTICK_DEADBAND && normalized < JOYSTICK_DEADBAND) {
    normalized = 0.0;
  }
  return normalized;
}

void setup() {
  Serial.begin(921600);
  Wire.begin();
  for (uint8_t index = 0; index < JOYSTICK_AXES; index++) {
    pinMode(JOYSTICK_PINS[index], INPUT);
  }
}

void loop() {
  float commands[OUTPUT_AXES];

  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    selectMuxChannel(ch);

    uint16_t raw = readRawAngle();
    float angle = raw * 360.0 / 4096.0;

    angle -= zeroOffset[ch];
    angle *= direction[ch];
    angle = wrapAngle(angle);
    angle = applyCalibration(angle, ch);
    angle = encoderToJointDeg(ch, angle);

    commands[ch] = angle;
  }

  // J6/J7: joystick normalized commands in [-1, 1] for continuous servos.
  commands[5] = readJoystickNormalized(0);
  commands[6] = readJoystickNormalized(1);

  // CSV for J1..J7.
  for (uint8_t ch = 0; ch < OUTPUT_AXES; ch++) {
    Serial.print(commands[ch], 3);
    if (ch + 1 < OUTPUT_AXES) {
      Serial.print(',');
    }
  }
  Serial.println();

  delay(20);
}