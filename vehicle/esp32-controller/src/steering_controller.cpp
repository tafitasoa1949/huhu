#include "steering_controller.h"

namespace steering {

namespace {

int clampInt(int value, int low, int high) {
    if (value < low) {
        return low;
    }
    if (value > high) {
        return high;
    }
    return value;
}

int absInt(int value) { return value < 0 ? -value : value; }

// value * numerator / denominator, arrondi au plus proche et symétrique
// autour de zéro. La division entière du C tronque vers zéro, ce qui ferait
// dériver les deux côtés différemment dès que l'un est négatif.
int scaleRounded(int value, int numerator, int denominator) {
    if (denominator == 0) {
        return 0;
    }
    const long product = static_cast<long>(value) * numerator;
    const long half = denominator / 2;
    if (product >= 0) {
        return static_cast<int>((product + half) / denominator);
    }
    return -static_cast<int>((-product + half) / denominator);
}

// Traduit une consigne logique en rapport cyclique réellement envoyé au pont
// en H : une consigne non nulle est comprimée dans
// [min_duty_pct, max_duty_pct] pour franchir le seuil de démarrage des
// moteurs sans dépasser le plafond de sécurité.
int commandToDuty(int command_pct, const MixerConfig& config) {
    if (command_pct == 0) {
        return 0;
    }

    const int max_duty = clampInt(config.max_duty_pct, 0, 100);
    const int min_duty = clampInt(config.min_duty_pct, 0, max_duty);

    const int magnitude = clampInt(absInt(command_pct), 0, 100);
    const int span = max_duty - min_duty;
    const int duty = min_duty + scaleRounded(magnitude, span, 100);

    return command_pct < 0 ? -duty : duty;
}

}  // namespace

WheelDuty mix(int speed_pct, int steering_pct, const MixerConfig& config) {
    const int speed = clampInt(speed_pct, 0, 100);
    const int steering = clampInt(steering_pct, -100, 100);

    // Vitesse nulle : la voiture est à l'arrêt, la direction ne doit pas la
    // faire pivoter (sauf si la rotation sur place est explicitement
    // autorisée par la configuration).
    if (speed == 0 && !config.allow_pivot) {
        return stopped();
    }

    // Écart appliqué entre les deux côtés. steering négatif = virage à
    // gauche : le côté gauche ralentit, le côté droit accélère.
    const int gain = clampInt(config.steering_gain_pct, 0, 100);
    const int turn = scaleRounded(steering, gain, 100);

    int left = speed + turn;
    int right = speed - turn;

    // Le mélange peut sortir de [-100, 100] (par exemple vitesse 60 et
    // direction -80). On remet les deux côtés à l'échelle plutôt que de les
    // écrêter : l'écrêtage écraserait le rapport entre les roues, donc le
    // rayon de braquage demandé.
    const int peak = absInt(left) > absInt(right) ? absInt(left) : absInt(right);
    if (peak > 100) {
        left = scaleRounded(left, 100, peak);
        right = scaleRounded(right, 100, peak);
    }

    WheelDuty duty;
    duty.left_pct = commandToDuty(left, config);
    duty.right_pct = commandToDuty(right, config);

    if (config.invert_left) {
        duty.left_pct = -duty.left_pct;
    }
    if (config.invert_right) {
        duty.right_pct = -duty.right_pct;
    }
    return duty;
}

WheelDuty stopped() {
    WheelDuty duty;
    duty.left_pct = 0;
    duty.right_pct = 0;
    return duty;
}

}  // namespace steering
