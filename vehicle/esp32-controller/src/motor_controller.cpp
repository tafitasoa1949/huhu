#include "motor_controller.h"

#include <Arduino.h>

#include "pin_config.h"

namespace motors {

namespace {

// Un canal moteur du L298N : une broche PWM d'activation et deux broches de
// sens. Regrouper les broches évite de dupliquer la logique pour la gauche
// et la droite.
struct Channel {
    int pwm_pin;
    int in1_pin;
    int in2_pin;
    int ledc_channel;
};

constexpr Channel LEFT = {PIN_MOTOR_LEFT_PWM, PIN_MOTOR_LEFT_IN1,
                          PIN_MOTOR_LEFT_IN2, MOTOR_PWM_CHANNEL_LEFT};
constexpr Channel RIGHT = {PIN_MOTOR_RIGHT_PWM, PIN_MOTOR_RIGHT_IN1,
                           PIN_MOTOR_RIGHT_IN2, MOTOR_PWM_CHANNEL_RIGHT};

constexpr int MAX_DUTY_TICKS = (1 << MOTOR_PWM_RESOLUTION_BITS) - 1;

int clampInt(int value, int low, int high) {
    if (value < low) {
        return low;
    }
    if (value > high) {
        return high;
    }
    return value;
}

// L'API LEDC a changé entre les cœurs Arduino-ESP32 2.x et 3.x. Ces deux
// enveloppes permettent au firmware de compiler avec l'un ou l'autre sans que
// personne ait à figer une version dans son environnement.
void ledcBegin(const Channel& channel) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcAttach(channel.pwm_pin, MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RESOLUTION_BITS);
#else
    ledcSetup(channel.ledc_channel, MOTOR_PWM_FREQ_HZ,
              MOTOR_PWM_RESOLUTION_BITS);
    ledcAttachPin(channel.pwm_pin, channel.ledc_channel);
#endif
}

void ledcSet(const Channel& channel, int ticks) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcWrite(channel.pwm_pin, ticks);
#else
    ledcWrite(channel.ledc_channel, ticks);
#endif
}

void applyChannel(const Channel& channel, int duty_pct) {
    duty_pct = clampInt(duty_pct, -100, 100);

    if (duty_pct == 0) {
        // Roue libre : les deux entrées de sens au même niveau bas et le PWM
        // à zéro désactivent la sortie du pont.
        digitalWrite(channel.in1_pin, LOW);
        digitalWrite(channel.in2_pin, LOW);
        ledcSet(channel, 0);
        return;
    }

    const bool forward = duty_pct > 0;
    digitalWrite(channel.in1_pin, forward ? HIGH : LOW);
    digitalWrite(channel.in2_pin, forward ? LOW : HIGH);

    const int magnitude = forward ? duty_pct : -duty_pct;
    const int ticks = (magnitude * MAX_DUTY_TICKS + 50) / 100;
    ledcSet(channel, ticks);
}

void brakeChannel(const Channel& channel) {
    // Les deux entrées au même niveau haut court-circuitent le moteur à
    // travers le pont, ce qui le freine. Le PWM doit rester actif pour que la
    // sortie ne soit pas simplement coupée.
    digitalWrite(channel.in1_pin, HIGH);
    digitalWrite(channel.in2_pin, HIGH);
    ledcSet(channel, MAX_DUTY_TICKS);
}

void beginChannel(const Channel& channel) {
    pinMode(channel.in1_pin, OUTPUT);
    pinMode(channel.in2_pin, OUTPUT);
    digitalWrite(channel.in1_pin, LOW);
    digitalWrite(channel.in2_pin, LOW);
    ledcBegin(channel);
    ledcSet(channel, 0);
}

}  // namespace

void begin() {
    beginChannel(LEFT);
    beginChannel(RIGHT);
    coast();
}

void applyDuty(const steering::WheelDuty& duty) {
    applyChannel(LEFT, duty.left_pct);
    applyChannel(RIGHT, duty.right_pct);
}

void coast() {
    applyChannel(LEFT, 0);
    applyChannel(RIGHT, 0);
}

void brake() {
    brakeChannel(LEFT);
    brakeChannel(RIGHT);
}

}  // namespace motors
