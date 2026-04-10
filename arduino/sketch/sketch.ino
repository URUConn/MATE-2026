#include <Wire.h>
#include <EEPROM.h>
#include <ctype.h>
#include <stdio.h>
#include <string.h>

#define MUX_ADDR 0x70
#define AS5600_ADDR 0x36
const uint8_t SENSOR_AXES = 5;  // J1..J5 from AS5600 sensors
const uint8_t OUTPUT_AXES = 7;  // J1..J7 published to ROS bridge
const uint8_t JOYSTICK_AXES = 2;
const unsigned long SENSOR_PERIOD_MS = 20;
const unsigned long STREAM_PERIOD_MS = 20;
const uint32_t CALIBRATION_MAGIC = 0x524F5631;  // 'ROV1'
const uint16_t CALIBRATION_VERSION = 1;

const uint8_t JOYSTICK_PINS[JOYSTICK_AXES] = {A0, A1};
const int JOYSTICK_DIRECTION[JOYSTICK_AXES] = {1, 1};
const float JOYSTICK_DEADBAND = 0.06;

// Physical joint limits (deg) for J1..J5.
const float JOINT_MAX_DEG[SENSOR_AXES] = {165.0, 119.0, 119.0, 270.0, 270.0};

// Active encoder span (deg) used to control each joint. Remaining span is deadzone.
// Setting this equal to joint max gives a 1:1 "encoder angle == joint angle" feel.
const float ENCODER_ACTIVE_DEG[SENSOR_AXES] = {165.0, 119.0, 119.0, 270.0, 270.0};

// Factory defaults (edit these to change out-of-box calibration).
const float FACTORY_ZERO_OFFSET[SENSOR_AXES] = {308.145, 117.686, 125.947, 0, 0};
const int FACTORY_DIRECTION[SENSOR_AXES] = {1, 1, 1, 1, 1};
const float FACTORY_CAL_DEG[SENSOR_AXES][4] = {
  {0, 90, 180, 270},
  {0, 90, 180, 270},
  {0, 90, 180, 270},
  {0, 90, 180, 270},
  {0, 90, 180, 270}
};
const bool FACTORY_TWOPT_ENABLED[SENSOR_AXES] = {true, true, true, false, false};
const bool FACTORY_TWOPT_MIN_SET[SENSOR_AXES] = {true, true, true, false, false};
const bool FACTORY_TWOPT_MAX_SET[SENSOR_AXES] = {true, true, true, false, false};
const float FACTORY_TWOPT_MIN_ENC_DEG[SENSOR_AXES] = {359.91, 359.82, 0.00, 0, 0};
const float FACTORY_TWOPT_MAX_ENC_DEG[SENSOR_AXES] = {172.71, 118.04, 249.52, 0, 0};
const float FACTORY_TWOPT_MIN_JOINT_DEG[SENSOR_AXES] = {0, 0, 0, 0, 0};
const float FACTORY_TWOPT_MAX_JOINT_DEG[SENSOR_AXES] = {165.0, 119.0, 119.0, 270.0, 270.0};

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

float lastRawDeg[SENSOR_AXES] = {0, 0, 0, 0, 0};
float lastEncoderDeg[SENSOR_AXES] = {0, 0, 0, 0, 0};
float lastCalibratedDeg[SENSOR_AXES] = {0, 0, 0, 0, 0};
float lastJointDeg[SENSOR_AXES] = {0, 0, 0, 0, 0};
uint32_t badReadCount[SENSOR_AXES] = {0, 0, 0, 0, 0};
bool lastReadValid[SENSOR_AXES] = {true, true, true, true, true};

bool twoPointEnabled[SENSOR_AXES] = {false, false, false, false, false};
bool twoPointMinSet[SENSOR_AXES] = {false, false, false, false, false};
bool twoPointMaxSet[SENSOR_AXES] = {false, false, false, false, false};
float twoPointMinEncDeg[SENSOR_AXES] = {0, 0, 0, 0, 0};
float twoPointMaxEncDeg[SENSOR_AXES] = {0, 0, 0, 0, 0};
float twoPointMinJointDeg[SENSOR_AXES] = {0, 0, 0, 0, 0};
float twoPointMaxJointDeg[SENSOR_AXES] = {0, 0, 0, 0, 0};
float commands[OUTPUT_AXES] = {0, 0, 0, 0, 0, 0, 0};

struct CalibrationData {
  uint32_t magic;
  uint16_t version;
  float zeroOffset[SENSOR_AXES];
  int8_t direction[SENSOR_AXES];
  float calDeg[SENSOR_AXES][4];
  uint8_t twoPointEnabled[SENSOR_AXES];
  uint8_t twoPointMinSet[SENSOR_AXES];
  uint8_t twoPointMaxSet[SENSOR_AXES];
  float twoPointMinEncDeg[SENSOR_AXES];
  float twoPointMaxEncDeg[SENSOR_AXES];
  float twoPointMinJointDeg[SENSOR_AXES];
  float twoPointMaxJointDeg[SENSOR_AXES];
};

// Clamp is enforced on onboard arm_servo_node; Arduino publishes calibrated angles only.

void selectMuxChannel(uint8_t ch) {
  Wire.beginTransmission(MUX_ADDR);
  Wire.write(1 << ch);
  Wire.endTransmission();
}

bool readRawAngle(uint16_t* rawOut) {
  Wire.beginTransmission(AS5600_ADDR);
  Wire.write(0x0C);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(AS5600_ADDR, (uint8_t)2) != 2) {
    return false;
  }

  int msb = Wire.read();
  int lsb = Wire.read();
  if (msb < 0 || lsb < 0) {
    return false;
  }

  // AS5600 RAW ANGLE is 12-bit.
  *rawOut = (uint16_t)(((uint16_t)msb << 8) | (uint16_t)lsb) & 0x0FFF;
  return true;
}

float wrapAngle(float a) {
  while (a < 0) a += 360;
  while (a >= 360) a -= 360;
  return a;
}

float wrapDelta(float fromDeg, float toDeg) {
  float d = toDeg - fromDeg;
  while (d < 0) d += 360;
  while (d >= 360) d -= 360;
  return d;
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

float twoPointEncoderToJointDeg(int ch, float encoderDeg) {
  float minEnc = wrapAngle(twoPointMinEncDeg[ch]);
  float maxEnc = wrapAngle(twoPointMaxEncDeg[ch]);
  float minJoint = twoPointMinJointDeg[ch];
  float maxJoint = twoPointMaxJointDeg[ch];

  float span = wrapDelta(minEnc, maxEnc);
  if (span <= 0.001) {
    return minJoint;
  }

  float pos = wrapDelta(minEnc, encoderDeg);
  if (pos <= span) {
    return minJoint + (pos / span) * (maxJoint - minJoint);
  }

  // In deadzone, hold the nearest endpoint to avoid jump near wrap.
  float deadzone = 360.0 - span;
  float deadPos = wrapDelta(maxEnc, encoderDeg);
  if (deadPos <= (deadzone * 0.5)) {
    return maxJoint;
  }
  return minJoint;
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

int toJointIndex(int jointNumber) {
  if (jointNumber < 1 || jointNumber > SENSOR_AXES) {
    Serial.println("# ERR invalid joint. Use 1..5.");
    return -1;
  }
  return jointNumber - 1;
}

int markerToIndex(int markerDeg) {
  if (markerDeg == 0) return 0;
  if (markerDeg == 90) return 1;
  if (markerDeg == 180) return 2;
  if (markerDeg == 270) return 3;
  return -1;
}

void printCalibrationHelp() {
  Serial.println("# Calibration commands (joint numbers are 1-based):");
  Serial.println("#   HELP");
  Serial.println("#   STATUS");
  Serial.println("#   ZERO ALL");
  Serial.println("#   ZERO <joint>");
  Serial.println("#   DIR <joint> <1|-1>");
  Serial.println("#   FLIP <joint>");
  Serial.println("#   CAL <joint> <0|90|180|270>   (capture current encoder angle)");
  Serial.println("#   CALSET <joint> <0|1|2|3> <deg>");
  Serial.println("#   SETMIN <joint> <joint_deg>   (capture current position as min endpoint)");
  Serial.println("#   SETMAX <joint> <joint_deg>   (capture current position as max endpoint)");
  Serial.println("#   SETMIN <joint>               (uses 0 deg)");
  Serial.println("#   SETMAX <joint>               (uses JOINT_MAX_DEG[joint])");
  Serial.println("#   MIN <joint> [joint_deg]      (alias of SETMIN)");
  Serial.println("#   MAX <joint> [joint_deg]      (alias of SETMAX)");
  Serial.println("#   TWOPT <joint> <0|1>          (disable/enable two-point mapping)");
  Serial.println("#   SAVE                         (store calibration in EEPROM)");
  Serial.println("#   LOAD                         (load calibration from EEPROM)");
  Serial.println("#   CLEAR                        (clear saved EEPROM calibration)");
  Serial.println("#   PRINT   (emit copy-paste arrays)");
}

void printCalibrationStatus() {
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    Serial.print("# J");
    Serial.print(ch + 1);
    Serial.print(" raw=");
    Serial.print(lastRawDeg[ch], 3);
    Serial.print(" enc=");
    Serial.print(lastEncoderDeg[ch], 3);
    Serial.print(" cal=");
    Serial.print(lastCalibratedDeg[ch], 3);
    Serial.print(" joint=");
    Serial.print(lastJointDeg[ch], 3);
    Serial.print(" zero=");
    Serial.print(zeroOffset[ch], 3);
    Serial.print(" dir=");
    Serial.print(direction[ch]);
    Serial.print(" i2c=");
    Serial.print(lastReadValid[ch] ? "ok" : "bad");
    Serial.print("(");
    Serial.print(badReadCount[ch]);
    Serial.print(")");
    Serial.print(" tp=");
    Serial.print(twoPointEnabled[ch] ? "on" : "off");
    if (twoPointMinSet[ch] && twoPointMaxSet[ch]) {
      Serial.print(" [");
      Serial.print(twoPointMinEncDeg[ch], 2);
      Serial.print("->");
      Serial.print(twoPointMaxEncDeg[ch], 2);
      Serial.print(" enc, ");
      Serial.print(twoPointMinJointDeg[ch], 1);
      Serial.print("->");
      Serial.print(twoPointMaxJointDeg[ch], 1);
      Serial.print(" deg]");
    }
    Serial.println();
  }
}

void printCalibrationArrays() {
  Serial.println("# zeroOffset:");
  Serial.print("float zeroOffset[SENSOR_AXES] = {");
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    if (ch > 0) Serial.print(", ");
    Serial.print(zeroOffset[ch], 3);
  }
  Serial.println("};");

  Serial.println("# direction:");
  Serial.print("int direction[SENSOR_AXES] = {");
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    if (ch > 0) Serial.print(", ");
    Serial.print(direction[ch]);
  }
  Serial.println("};");

  Serial.println("# calDeg:");
  Serial.println("float calDeg[SENSOR_AXES][4] = {");
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    Serial.print("  {");
    for (uint8_t i = 0; i < 4; i++) {
      if (i > 0) Serial.print(", ");
      Serial.print(calDeg[ch][i], 3);
    }
    if (ch + 1 < SENSOR_AXES) {
      Serial.println("},");
    } else {
      Serial.println("}");
    }
  }
  Serial.println("};");

  Serial.println("# twoPointEnabled:");
  Serial.print("bool twoPointEnabled[SENSOR_AXES] = {");
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    if (ch > 0) Serial.print(", ");
    Serial.print(twoPointEnabled[ch] ? "true" : "false");
  }
  Serial.println("};");

  Serial.println("# twoPointMinEncDeg:");
  Serial.print("float twoPointMinEncDeg[SENSOR_AXES] = {");
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    if (ch > 0) Serial.print(", ");
    Serial.print(twoPointMinEncDeg[ch], 3);
  }
  Serial.println("};");

  Serial.println("# twoPointMaxEncDeg:");
  Serial.print("float twoPointMaxEncDeg[SENSOR_AXES] = {");
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    if (ch > 0) Serial.print(", ");
    Serial.print(twoPointMaxEncDeg[ch], 3);
  }
  Serial.println("};");

  Serial.println("# twoPointMinJointDeg:");
  Serial.print("float twoPointMinJointDeg[SENSOR_AXES] = {");
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    if (ch > 0) Serial.print(", ");
    Serial.print(twoPointMinJointDeg[ch], 3);
  }
  Serial.println("};");

  Serial.println("# twoPointMaxJointDeg:");
  Serial.print("float twoPointMaxJointDeg[SENSOR_AXES] = {");
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    if (ch > 0) Serial.print(", ");
    Serial.print(twoPointMaxJointDeg[ch], 3);
  }
  Serial.println("};");
}

void saveCalibrationToEeprom() {
  CalibrationData data;
  data.magic = CALIBRATION_MAGIC;
  data.version = CALIBRATION_VERSION;

  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    data.zeroOffset[ch] = zeroOffset[ch];
    data.direction[ch] = (direction[ch] >= 0) ? 1 : -1;
    data.twoPointEnabled[ch] = twoPointEnabled[ch] ? 1 : 0;
    data.twoPointMinSet[ch] = twoPointMinSet[ch] ? 1 : 0;
    data.twoPointMaxSet[ch] = twoPointMaxSet[ch] ? 1 : 0;
    data.twoPointMinEncDeg[ch] = twoPointMinEncDeg[ch];
    data.twoPointMaxEncDeg[ch] = twoPointMaxEncDeg[ch];
    data.twoPointMinJointDeg[ch] = twoPointMinJointDeg[ch];
    data.twoPointMaxJointDeg[ch] = twoPointMaxJointDeg[ch];
    for (uint8_t i = 0; i < 4; i++) {
      data.calDeg[ch][i] = calDeg[ch][i];
    }
  }

  EEPROM.put(0, data);
  Serial.println("# OK calibration saved to EEPROM.");
}

bool loadCalibrationFromEeprom() {
  CalibrationData data;
  EEPROM.get(0, data);

  if (data.magic != CALIBRATION_MAGIC || data.version != CALIBRATION_VERSION) {
    return false;
  }

  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    zeroOffset[ch] = data.zeroOffset[ch];
    direction[ch] = (data.direction[ch] >= 0) ? 1 : -1;
    twoPointEnabled[ch] = (data.twoPointEnabled[ch] != 0);
    twoPointMinSet[ch] = (data.twoPointMinSet[ch] != 0);
    twoPointMaxSet[ch] = (data.twoPointMaxSet[ch] != 0);
    twoPointMinEncDeg[ch] = data.twoPointMinEncDeg[ch];
    twoPointMaxEncDeg[ch] = data.twoPointMaxEncDeg[ch];
    twoPointMinJointDeg[ch] = data.twoPointMinJointDeg[ch];
    twoPointMaxJointDeg[ch] = data.twoPointMaxJointDeg[ch];
    for (uint8_t i = 0; i < 4; i++) {
      calDeg[ch][i] = data.calDeg[ch][i];
    }
  }

  return true;
}

void clearCalibrationEeprom() {
  CalibrationData data;
  data.magic = 0;
  data.version = 0;
  EEPROM.put(0, data);
  Serial.println("# OK calibration EEPROM header cleared.");
}

void applyFactoryCalibrationDefaults() {
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    zeroOffset[ch] = FACTORY_ZERO_OFFSET[ch];
    direction[ch] = FACTORY_DIRECTION[ch];
    twoPointEnabled[ch] = FACTORY_TWOPT_ENABLED[ch];
    twoPointMinSet[ch] = FACTORY_TWOPT_MIN_SET[ch];
    twoPointMaxSet[ch] = FACTORY_TWOPT_MAX_SET[ch];
    twoPointMinEncDeg[ch] = FACTORY_TWOPT_MIN_ENC_DEG[ch];
    twoPointMaxEncDeg[ch] = FACTORY_TWOPT_MAX_ENC_DEG[ch];
    twoPointMinJointDeg[ch] = FACTORY_TWOPT_MIN_JOINT_DEG[ch];
    twoPointMaxJointDeg[ch] = FACTORY_TWOPT_MAX_JOINT_DEG[ch];

    for (uint8_t i = 0; i < 4; i++) {
      calDeg[ch][i] = FACTORY_CAL_DEG[ch][i];
    }
  }
}

void processCalibrationCommand(char* line) {
  while (*line == ' ' || *line == '\t') line++;
  if (*line == '\0') return;

  for (char* p = line; *p; p++) {
    *p = toupper(*p);
  }

  int jointNumber = 0;
  int markerDeg = 0;
  int sign = 0;
  int calIndex = 0;
  float value = 0.0;
  int enabled = 0;

  if (strcmp(line, "HELP") == 0) {
    printCalibrationHelp();
    return;
  }

  if (strcmp(line, "STATUS") == 0) {
    printCalibrationStatus();
    return;
  }

  if (strcmp(line, "ZERO ALL") == 0) {
    for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
      zeroOffset[ch] = lastRawDeg[ch];
    }
    Serial.println("# OK zeroOffset set from current raw angles for all joints.");
    return;
  }

  if (strcmp(line, "PRINT") == 0) {
    printCalibrationArrays();
    return;
  }

  if (strcmp(line, "SAVE") == 0) {
    saveCalibrationToEeprom();
    return;
  }

  if (strcmp(line, "LOAD") == 0) {
    if (loadCalibrationFromEeprom()) {
      Serial.println("# OK calibration loaded from EEPROM.");
    } else {
      Serial.println("# ERR no valid EEPROM calibration found.");
    }
    return;
  }

  if (strcmp(line, "CLEAR") == 0) {
    clearCalibrationEeprom();
    return;
  }

  if (sscanf(line, "ZERO %d", &jointNumber) == 1) {
    int idx = toJointIndex(jointNumber);
    if (idx < 0) return;
    zeroOffset[idx] = lastRawDeg[idx];
    Serial.print("# OK J");
    Serial.print(jointNumber);
    Serial.print(" zeroOffset=");
    Serial.println(zeroOffset[idx], 3);
    return;
  }

  if (sscanf(line, "DIR %d %d", &jointNumber, &sign) == 2) {
    int idx = toJointIndex(jointNumber);
    if (idx < 0) return;
    if (sign != 1 && sign != -1) {
      Serial.println("# ERR direction must be 1 or -1.");
      return;
    }
    direction[idx] = sign;
    Serial.print("# OK J");
    Serial.print(jointNumber);
    Serial.print(" direction=");
    Serial.println(direction[idx]);
    return;
  }

  if (sscanf(line, "FLIP %d", &jointNumber) == 1) {
    int idx = toJointIndex(jointNumber);
    if (idx < 0) return;
    direction[idx] *= -1;
    Serial.print("# OK J");
    Serial.print(jointNumber);
    Serial.print(" direction=");
    Serial.println(direction[idx]);
    return;
  }

  if (sscanf(line, "CAL %d %d", &jointNumber, &markerDeg) == 2) {
    int idx = toJointIndex(jointNumber);
    if (idx < 0) return;
    int markerIndex = markerToIndex(markerDeg);
    if (markerIndex < 0) {
      Serial.println("# ERR marker must be 0, 90, 180, or 270.");
      return;
    }
    calDeg[idx][markerIndex] = lastEncoderDeg[idx];
    Serial.print("# OK J");
    Serial.print(jointNumber);
    Serial.print(" calDeg[");
    Serial.print(markerIndex);
    Serial.print("]=");
    Serial.println(calDeg[idx][markerIndex], 3);
    return;
  }

  if (sscanf(line, "CALSET %d %d %f", &jointNumber, &calIndex, &value) == 3) {
    int idx = toJointIndex(jointNumber);
    if (idx < 0) return;
    if (calIndex < 0 || calIndex > 3) {
      Serial.println("# ERR CALSET index must be 0..3.");
      return;
    }
    calDeg[idx][calIndex] = value;
    Serial.print("# OK J");
    Serial.print(jointNumber);
    Serial.print(" calDeg[");
    Serial.print(calIndex);
    Serial.print("]=");
    Serial.println(calDeg[idx][calIndex], 3);
    return;
  }

  if (strncmp(line, "SETMIN", 6) == 0 || strncmp(line, "MIN", 3) == 0) {
    int parsed = sscanf(line, "SETMIN %d %f", &jointNumber, &value);
    if (parsed < 1) {
      parsed = sscanf(line, "MIN %d %f", &jointNumber, &value);
    }
    if (parsed >= 1) {
      int idx = toJointIndex(jointNumber);
      if (idx < 0) return;
      if (parsed == 1) {
        value = 0.0;
      }
      twoPointMinEncDeg[idx] = lastEncoderDeg[idx];
      twoPointMinJointDeg[idx] = value;
      twoPointMinSet[idx] = true;
      if (twoPointMinSet[idx] && twoPointMaxSet[idx]) {
        twoPointEnabled[idx] = true;
      }
      Serial.print("# OK J");
      Serial.print(jointNumber);
      Serial.print(" min endpoint enc=");
      Serial.print(twoPointMinEncDeg[idx], 3);
      Serial.print(" joint=");
      Serial.println(twoPointMinJointDeg[idx], 3);
      return;
    }
  }

  if (strncmp(line, "SETMAX", 6) == 0 || strncmp(line, "MAX", 3) == 0) {
    int parsed = sscanf(line, "SETMAX %d %f", &jointNumber, &value);
    if (parsed < 1) {
      parsed = sscanf(line, "MAX %d %f", &jointNumber, &value);
    }
    if (parsed >= 1) {
      int idx = toJointIndex(jointNumber);
      if (idx < 0) return;
      if (parsed == 1) {
        value = JOINT_MAX_DEG[idx];
      }
      twoPointMaxEncDeg[idx] = lastEncoderDeg[idx];
      twoPointMaxJointDeg[idx] = value;
      twoPointMaxSet[idx] = true;
      if (twoPointMinSet[idx] && twoPointMaxSet[idx]) {
        twoPointEnabled[idx] = true;
      }
      Serial.print("# OK J");
      Serial.print(jointNumber);
      Serial.print(" max endpoint enc=");
      Serial.print(twoPointMaxEncDeg[idx], 3);
      Serial.print(" joint=");
      Serial.println(twoPointMaxJointDeg[idx], 3);
      return;
    }
  }

  if (sscanf(line, "TWOPT %d %d", &jointNumber, &enabled) == 2) {
    int idx = toJointIndex(jointNumber);
    if (idx < 0) return;
    if (enabled != 0 && enabled != 1) {
      Serial.println("# ERR TWOPT value must be 0 or 1.");
      return;
    }
    if (enabled == 1 && !(twoPointMinSet[idx] && twoPointMaxSet[idx])) {
      Serial.println("# ERR set endpoints first with SETMIN and SETMAX.");
      return;
    }
    twoPointEnabled[idx] = (enabled == 1);
    Serial.print("# OK J");
    Serial.print(jointNumber);
    Serial.print(" two-point=");
    Serial.println(twoPointEnabled[idx] ? "on" : "off");
    return;
  }

  Serial.println("# ERR unknown command. Type HELP.");
}

void handleCalibrationSerial() {
  static char buffer[96];
  static uint8_t length = 0;

  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\r') {
      continue;
    }

    if (c == '\n') {
      buffer[length] = '\0';
      processCalibrationCommand(buffer);
      length = 0;
      continue;
    }

    if (length + 1 < sizeof(buffer)) {
      buffer[length++] = c;
    }
  }
}

void setup() {
  Serial.begin(921600);
  Wire.begin();
  applyFactoryCalibrationDefaults();
  for (uint8_t index = 0; index < JOYSTICK_AXES; index++) {
    pinMode(JOYSTICK_PINS[index], INPUT);
  }
  bool loadedFromEeprom = loadCalibrationFromEeprom();
  if (loadedFromEeprom) {
    Serial.println("# Loaded calibration from EEPROM.");
  } else {
    Serial.println("# No valid EEPROM calibration found; using in-code defaults.");
  }
  Serial.print("# CAL SOURCE: ");
  Serial.println(loadedFromEeprom ? "EEPROM" : "FACTORY_DEFAULTS");
  Serial.println("# Encoder stream ready. Type HELP for calibration commands.");
}

void updateJointCommands() {
  for (uint8_t ch = 0; ch < SENSOR_AXES; ch++) {
    selectMuxChannel(ch);

    uint16_t raw = 0;
    if (!readRawAngle(&raw)) {
      badReadCount[ch]++;
      lastReadValid[ch] = false;
      // Hold last valid output for this joint when sensor read fails.
      commands[ch] = lastJointDeg[ch];
      continue;
    }
    lastReadValid[ch] = true;

    float rawDeg = raw * 360.0 / 4096.0;
    float encoderDeg = rawDeg;

    encoderDeg -= zeroOffset[ch];
    encoderDeg *= direction[ch];
    encoderDeg = wrapAngle(encoderDeg);

    float calibratedDeg = applyCalibration(encoderDeg, ch);
    float jointDeg = encoderToJointDeg(ch, calibratedDeg);
    if (twoPointEnabled[ch] && twoPointMinSet[ch] && twoPointMaxSet[ch]) {
      jointDeg = twoPointEncoderToJointDeg(ch, encoderDeg);
      calibratedDeg = encoderDeg;
    }

    lastRawDeg[ch] = rawDeg;
    lastEncoderDeg[ch] = encoderDeg;
    lastCalibratedDeg[ch] = calibratedDeg;
    lastJointDeg[ch] = jointDeg;

    commands[ch] = jointDeg;
  }

  // J6/J7: joystick normalized commands in [-1, 1] for continuous servos.
  commands[5] = readJoystickNormalized(0);
  commands[6] = readJoystickNormalized(1);
}

void publishCommandsCsv() {
  for (uint8_t ch = 0; ch < OUTPUT_AXES; ch++) {
    Serial.print(commands[ch], 3);
    if (ch + 1 < OUTPUT_AXES) {
      Serial.print(',');
    }
  }
  Serial.println();
}

void loop() {
  static unsigned long lastSensorUpdateMs = 0;
  static unsigned long lastStreamMs = 0;
  unsigned long now = millis();

  handleCalibrationSerial();

  if (now - lastSensorUpdateMs >= SENSOR_PERIOD_MS) {
    lastSensorUpdateMs = now;
    updateJointCommands();
  }

  if (now - lastStreamMs >= STREAM_PERIOD_MS) {
    lastStreamMs = now;
    publishCommandsCsv();
  }
}