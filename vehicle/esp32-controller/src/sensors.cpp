#include "sensors.h"

#include <Arduino.h>

#include "pin_config.h"

namespace sensors {

namespace {

constexpr Reading UNKNOWN = {false, 0.0f};

Reading known(float value) { return Reading{true, value}; }

// --------------------------------------------------------------------------
// Bouton d'arrêt d'urgence
// --------------------------------------------------------------------------
#if ENABLE_EMERGENCY_BUTTON
// Un contact mécanique rebondit pendant quelques millisecondes. On ne retient
// un changement d'état que s'il se maintient : un rebond ne doit pas être lu
// comme un appui, ni un appui réel comme un rebond.
constexpr uint32_t BUTTON_DEBOUNCE_MS = 30;

bool button_stable_state = false;
bool button_last_raw = false;
uint32_t button_changed_ms = 0;

void updateButton(uint32_t now_ms) {
    // Câblage INPUT_PULLUP : le bouton relie la broche à la masse, donc
    // l'état bas correspond à l'appui.
    const bool raw = digitalRead(PIN_EMERGENCY_BUTTON) == LOW;
    if (raw != button_last_raw) {
        button_last_raw = raw;
        button_changed_ms = now_ms;
        return;
    }
    if (now_ms - button_changed_ms >= BUTTON_DEBOUNCE_MS) {
        button_stable_state = raw;
    }
}
#endif

// --------------------------------------------------------------------------
// Télémètre à ultrasons HC-SR04
// --------------------------------------------------------------------------
#if ENABLE_ULTRASONIC
// Cadence de mesure. Un écho met jusqu'à 25 ms à revenir sur la portée utile,
// et deux mesures trop rapprochées se parasitent l'une l'autre.
constexpr uint32_t ULTRASONIC_PERIOD_MS = 50;

// Vitesse du son à 20 °C, en mètres par microseconde, divisée par deux car
// l'onde fait l'aller et le retour.
constexpr float METERS_PER_MICROSECOND = 0.000343f / 2.0f;

// Au-delà de la portée utile, l'écho ne revient pas : on borne l'attente
// plutôt que de bloquer la boucle de contrôle.
constexpr uint32_t ECHO_TIMEOUT_US =
    static_cast<uint32_t>(ULTRASONIC_MAX_DISTANCE_M /
                         METERS_PER_MICROSECOND);

Reading ultrasonic_reading = UNKNOWN;
uint32_t ultrasonic_last_ms = 0;

void updateUltrasonic(uint32_t now_ms) {
    if (now_ms - ultrasonic_last_ms < ULTRASONIC_PERIOD_MS) {
        return;
    }
    ultrasonic_last_ms = now_ms;

    digitalWrite(PIN_ULTRASONIC_TRIG, LOW);
    delayMicroseconds(2);
    digitalWrite(PIN_ULTRASONIC_TRIG, HIGH);
    delayMicroseconds(10);
    digitalWrite(PIN_ULTRASONIC_TRIG, LOW);

    const uint32_t echo_us =
        pulseIn(PIN_ULTRASONIC_ECHO, HIGH, ECHO_TIMEOUT_US);
    if (echo_us == 0) {
        // Aucun écho : rien devant, ou hors de portée. Dans les deux cas la
        // distance est inconnue, elle ne doit surtout pas être lue comme 0.
        ultrasonic_reading = UNKNOWN;
        return;
    }

    ultrasonic_reading = known(echo_us * METERS_PER_MICROSECOND);
}
#endif

// --------------------------------------------------------------------------
// Encodeurs de roue
// --------------------------------------------------------------------------
#if ENABLE_ENCODERS
// Fenêtre de comptage. Plus elle est longue, plus la mesure est stable mais
// tardive ; 100 ms donne dix rafraîchissements par seconde.
constexpr uint32_t ENCODER_WINDOW_MS = 100;

volatile uint32_t encoder_left_ticks = 0;
volatile uint32_t encoder_right_ticks = 0;

uint32_t encoder_window_start_ms = 0;
uint32_t encoder_left_last = 0;
uint32_t encoder_right_last = 0;

Reading left_rpm_reading = UNKNOWN;
Reading right_rpm_reading = UNKNOWN;

void IRAM_ATTR onLeftTick() { ++encoder_left_ticks; }
void IRAM_ATTR onRightTick() { ++encoder_right_ticks; }

float ticksToRpm(uint32_t ticks, uint32_t elapsed_ms) {
    if (elapsed_ms == 0) {
        return 0.0f;
    }
    const float revolutions =
        static_cast<float>(ticks) / ENCODER_TICKS_PER_REVOLUTION;
    const float minutes = static_cast<float>(elapsed_ms) / 60000.0f;
    return revolutions / minutes;
}

void updateEncoders(uint32_t now_ms) {
    const uint32_t elapsed = now_ms - encoder_window_start_ms;
    if (elapsed < ENCODER_WINDOW_MS) {
        return;
    }

    // Lecture atomique des compteurs incrémentés sous interruption.
    noInterrupts();
    const uint32_t left_total = encoder_left_ticks;
    const uint32_t right_total = encoder_right_ticks;
    interrupts();

    left_rpm_reading = known(ticksToRpm(left_total - encoder_left_last, elapsed));
    right_rpm_reading =
        known(ticksToRpm(right_total - encoder_right_last, elapsed));

    encoder_left_last = left_total;
    encoder_right_last = right_total;
    encoder_window_start_ms = now_ms;
}
#endif

// --------------------------------------------------------------------------
// Tension batterie
// --------------------------------------------------------------------------
#if ENABLE_BATTERY_MONITOR
constexpr uint32_t BATTERY_PERIOD_MS = 1000;

Reading battery_reading = UNKNOWN;
uint32_t battery_last_ms = 0;

void updateBattery(uint32_t now_ms) {
    if (battery_last_ms != 0 && now_ms - battery_last_ms < BATTERY_PERIOD_MS) {
        return;
    }
    battery_last_ms = now_ms;

    // analogReadMilliVolts applique la correction d'étalonnage gravée en
    // usine : bien plus juste que de convertir soi-même les pas de l'ADC.
    const float adc_volts = analogReadMilliVolts(PIN_BATTERY_ADC) / 1000.0f;
    const float battery_volts = adc_volts * BATTERY_DIVIDER_RATIO;

    const float span = BATTERY_FULL_V - BATTERY_EMPTY_V;
    float pct = span > 0.0f ? (battery_volts - BATTERY_EMPTY_V) / span * 100.0f
                            : 0.0f;
    if (pct < 0.0f) {
        pct = 0.0f;
    }
    if (pct > 100.0f) {
        pct = 100.0f;
    }
    battery_reading = known(pct);
}
#endif

}  // namespace

void begin() {
#if ENABLE_EMERGENCY_BUTTON
    pinMode(PIN_EMERGENCY_BUTTON, INPUT_PULLUP);
#endif

#if ENABLE_ULTRASONIC
    pinMode(PIN_ULTRASONIC_TRIG, OUTPUT);
    pinMode(PIN_ULTRASONIC_ECHO, INPUT);
    digitalWrite(PIN_ULTRASONIC_TRIG, LOW);
#endif

#if ENABLE_ENCODERS
    pinMode(PIN_ENCODER_LEFT, INPUT_PULLUP);
    pinMode(PIN_ENCODER_RIGHT, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_ENCODER_LEFT), onLeftTick,
                    RISING);
    attachInterrupt(digitalPinToInterrupt(PIN_ENCODER_RIGHT), onRightTick,
                    RISING);
#endif
}

void update(uint32_t now_ms) {
#if ENABLE_EMERGENCY_BUTTON
    updateButton(now_ms);
#endif
#if ENABLE_ULTRASONIC
    updateUltrasonic(now_ms);
#endif
#if ENABLE_ENCODERS
    updateEncoders(now_ms);
#endif
#if ENABLE_BATTERY_MONITOR
    updateBattery(now_ms);
#endif

#if !ENABLE_EMERGENCY_BUTTON && !ENABLE_ULTRASONIC && !ENABLE_ENCODERS && \
    !ENABLE_BATTERY_MONITOR
    (void)now_ms;
#endif
}

bool emergencyButtonPressed() {
#if ENABLE_EMERGENCY_BUTTON
    return button_stable_state;
#else
    return false;
#endif
}

Reading obstacleDistanceM() {
#if ENABLE_ULTRASONIC
    return ultrasonic_reading;
#else
    return UNKNOWN;
#endif
}

Reading leftRpm() {
#if ENABLE_ENCODERS
    return left_rpm_reading;
#else
    return UNKNOWN;
#endif
}

Reading rightRpm() {
#if ENABLE_ENCODERS
    return right_rpm_reading;
#else
    return UNKNOWN;
#endif
}

Reading batteryPct() {
#if ENABLE_BATTERY_MONITOR
    return battery_reading;
#else
    return UNKNOWN;
#endif
}

}  // namespace sensors
