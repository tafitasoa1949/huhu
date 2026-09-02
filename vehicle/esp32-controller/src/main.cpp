#include <Arduino.h>

#include "communication.h"
#include "motor_controller.h"
#include "pin_config.h"
#include "protocol.h"
#include "safety.h"
#include "sensors.h"
#include "steering_controller.h"

// Firmware du contrôleur moteur.
//
// Boucle : lire une ligne JSON venant du Raspberry Pi, la valider, arbitrer la
// sécurité, appliquer la consigne aux moteurs, répondre une télémétrie.
// Aucune étape ne bloque : la surveillance du silence doit continuer de
// tourner même quand plus rien n'arrive sur le port série, puisque c'est
// précisément le cas qu'elle doit détecter.

namespace {

// --------------------------------------------------------------------------
// Cadence
// --------------------------------------------------------------------------
// Le protocole prévoit une télémétrie en réponse à chaque commande. On ajoute
// un battement périodique en l'absence de commande, pour que le Raspberry Pi
// voie l'ESP32 basculer en COMMAND_TIMEOUT au lieu de constater seulement un
// silence, qu'il ne saurait pas distinguer d'un câble débranché.
constexpr uint32_t HEARTBEAT_PERIOD_MS = 250;

// --------------------------------------------------------------------------
// État courant
// --------------------------------------------------------------------------
char line_buffer[protocol::MAX_LINE_LENGTH];
size_t line_length = 0;
bool line_overflow = false;

protocol::DriveMessage last_command = {0, 0, 0, false};
bool has_received_command = false;
uint32_t last_command_ms = 0;

// Vrai tant qu'une ligne rejetée n'a pas été suivie d'une ligne valide. Une
// erreur de protocole maintient les moteurs à l'arrêt : elle ne doit pas
// s'effacer d'elle-même.
bool last_line_rejected = false;
const char* last_error = nullptr;

uint32_t last_telemetry_ms = 0;

// Configuration de calibration, modifiable à chaud par une ligne CONFIG.
//
// Initialisée avec les valeurs de pin_config.h, qui restent la référence
// après un redémarrage. Le Raspberry Pi renvoie son profil à chaque
// connexion : il n'y a donc qu'une source de vérité, versionnée dans le
// dépôt, et rien n'est écrit dans la mémoire flash de la carte.
steering::MixerConfig active_config = [] {
    steering::MixerConfig config;
    config.steering_gain_pct = STEERING_GAIN_PCT;
    config.min_duty_pct = MOTOR_MIN_DUTY_PCT;
    config.max_duty_pct = MOTOR_MAX_DUTY_PCT;
    config.invert_left = MOTOR_LEFT_INVERT != 0;
    config.invert_right = MOTOR_RIGHT_INVERT != 0;
    return config;
}();

// Essai moteur en cours. Sert à vérifier le sens de rotation roue par roue,
// ce qu'une commande DRIVE ne permet pas puisqu'elle agit forcément sur les
// deux côtés à la fois.
bool test_active = false;
uint32_t test_until_ms = 0;
steering::WheelDuty test_duty;

// --------------------------------------------------------------------------
// Télémétrie
// --------------------------------------------------------------------------
void sendTelemetry(long sequence, const char* error) {
    protocol::TelemetryMessage telemetry;
    telemetry.sequence = sequence;
    telemetry.status = error == nullptr ? protocol::STATUS_OK
                                        : protocol::STATUS_ERROR;
    telemetry.error = error;

    const sensors::Reading distance = sensors::obstacleDistanceM();
    telemetry.has_obstacle_distance = distance.valid;
    telemetry.obstacle_distance_m = distance.value;

    const sensors::Reading battery = sensors::batteryPct();
    telemetry.has_battery = battery.valid;
    telemetry.battery_pct = static_cast<int>(battery.value + 0.5f);

    const sensors::Reading left = sensors::leftRpm();
    const sensors::Reading right = sensors::rightRpm();
    telemetry.has_rpm = left.valid && right.valid;
    telemetry.left_rpm = left.value;
    telemetry.right_rpm = right.value;

    char buffer[protocol::MAX_TELEMETRY_LENGTH];
    const size_t written =
        communication::buildTelemetryLine(telemetry, buffer, sizeof(buffer));
    if (written > 0) {
        Serial.write(buffer, written);
    }

    last_telemetry_ms = static_cast<uint32_t>(millis());
}

// --------------------------------------------------------------------------
// Réception
// --------------------------------------------------------------------------
void sendConfig(long sequence) {
    char buffer[protocol::MAX_TELEMETRY_LENGTH];
    const size_t written = communication::buildConfigLine(
        sequence, active_config.steering_gain_pct, active_config.min_duty_pct,
        active_config.max_duty_pct, active_config.invert_left,
        active_config.invert_right, buffer, sizeof(buffer));
    if (written > 0) {
        Serial.write(buffer, written);
    }
}

void applyConfig(const protocol::ConfigMessage& message) {
    // Mise à jour partielle : une ligne CONFIG ne modifie que ce qu'elle
    // mentionne. On peut ainsi corriger l'inversion d'un moteur sans risquer
    // d'écraser un seuil trouvé dix secondes plus tôt.
    if (message.has_steering_gain) {
        active_config.steering_gain_pct = message.steering_gain_pct;
    }
    if (message.has_min_duty) {
        active_config.min_duty_pct = message.min_duty_pct;
    }
    if (message.has_max_duty) {
        active_config.max_duty_pct = message.max_duty_pct;
    }
    if (message.has_invert_left) {
        active_config.invert_left = message.invert_left;
    }
    if (message.has_invert_right) {
        active_config.invert_right = message.invert_right;
    }

    // Changer la calibration en pleine conduite serait le meilleur moyen de
    // faire partir la voiture de travers : on repasse par l'arrêt.
    last_command.speed_pct = 0;
    last_command.steering_pct = 0;
    test_active = false;

    // On renvoie ce qui a été retenu, après bornage. Le Raspberry Pi vérifie
    // plutôt que de supposer que sa demande a été suivie.
    sendConfig(message.sequence);
}

void startTest(const protocol::TestMessage& message) {
    const int duty = message.duty_pct;

    // L'essai applique l'inversion — c'est tout l'intérêt de la boucle
    // « je teste, j'inverse, je re-teste » — mais **pas** le plafond de
    // vitesse ni le seuil de démarrage : chercher à quel rapport cyclique
    // une roue commence à tourner n'aurait aucun sens si la valeur demandée
    // était elle-même remise à l'échelle.
    int left = 0;
    int right = 0;
    if (message.target == protocol::TestTarget::Left ||
        message.target == protocol::TestTarget::Both) {
        left = active_config.invert_left ? -duty : duty;
    }
    if (message.target == protocol::TestTarget::Right ||
        message.target == protocol::TestTarget::Both) {
        right = active_config.invert_right ? -duty : duty;
    }

    test_duty.left_pct = left;
    test_duty.right_pct = right;
    test_active = true;
    test_until_ms = static_cast<uint32_t>(millis()) + message.duration_ms;

    // Après l'essai, la voiture doit être à l'arrêt et non repartir sur la
    // dernière consigne de conduite reçue.
    last_command.speed_pct = 0;
    last_command.steering_pct = 0;
    last_command.emergency = false;
}

void handleLine(const char* line) {
    protocol::ParsedMessage message;
    const protocol::ParseStatus status = communication::parseLine(line, message);

    if (status != protocol::ParseStatus::Ok) {
        // Ligne refusée : on n'applique rien et on garde les moteurs coupés
        // jusqu'à réception d'une commande valide (section 5.5).
        last_line_rejected = true;
        last_error = protocol::errorCodeFor(status);
        sendTelemetry(has_received_command ? last_command.sequence : 0,
                      last_error);
        return;
    }

    last_line_rejected = false;
    last_error = nullptr;
    has_received_command = true;
    last_command_ms = static_cast<uint32_t>(millis());

    switch (message.type) {
        case protocol::MessageType::Drive:
            // Une consigne de conduite annule un essai en cours.
            test_active = false;
            last_command = message.drive;
            break;

        case protocol::MessageType::Config:
            last_command.sequence = message.config.sequence;
            applyConfig(message.config);
            break;

        case protocol::MessageType::Test:
            last_command.sequence = message.test.sequence;
            startTest(message.test);
            break;
    }
}

// Lit le port série caractère par caractère. Serial.readStringUntil() aurait
// été plus court mais bloque jusqu'à son propre délai d'attente, ce qui
// suspendrait le watchdog au moment précis où on a besoin de lui.
void readSerial() {
    while (Serial.available() > 0) {
        const int value = Serial.read();
        if (value < 0) {
            return;
        }
        const char character = static_cast<char>(value);

        if (character == '\r') {
            continue;
        }

        if (character != '\n') {
            if (line_length + 1 < sizeof(line_buffer)) {
                line_buffer[line_length++] = character;
            } else {
                // Ligne anormalement longue : on continue de consommer les
                // octets jusqu'au saut de ligne pour se resynchroniser, mais
                // la ligne est perdue.
                line_overflow = true;
            }
            continue;
        }

        line_buffer[line_length] = '\0';

        if (line_overflow) {
            last_line_rejected = true;
            last_error = protocol::ERROR_LINE_TOO_LONG;
            sendTelemetry(has_received_command ? last_command.sequence : 0,
                          last_error);
        } else if (line_length > 0) {
            handleLine(line_buffer);
        }

        line_length = 0;
        line_overflow = false;
    }
}

// --------------------------------------------------------------------------
// Application des consignes
// --------------------------------------------------------------------------
safety::Decision arbitrate(uint32_t now_ms) {
    const sensors::Reading distance = sensors::obstacleDistanceM();

    safety::Inputs inputs;
    inputs.now_ms = now_ms;
    inputs.timeout_ms = protocol::COMMAND_TIMEOUT_MS;
    inputs.has_received_command = has_received_command;
    inputs.last_command_ms = last_command_ms;
    inputs.commanded_emergency = last_command.emergency;
    inputs.last_line_rejected = last_line_rejected;
    inputs.button_pressed = sensors::emergencyButtonPressed();
    inputs.has_local_distance = distance.valid;
    inputs.local_distance_m = distance.value;
    inputs.critical_distance_m = ULTRASONIC_CRITICAL_DISTANCE_M;
    return safety::evaluate(inputs);
}

void applyDecision(const safety::Decision& decision, uint32_t now_ms) {
    if (!decision.motors_allowed) {
        // La sécurité prime sur tout, y compris sur un essai de calibration.
        test_active = false;
        switch (decision.state) {
            case safety::State::ButtonPressed:
            case safety::State::EmergencyCommand:
            case safety::State::LocalObstacle:
                // Urgence : la distance d'arrêt prime sur la douceur.
                motors::brake();
                break;
            default:
                motors::coast();
                break;
        }
        return;
    }

    if (test_active) {
        // « now_ms a-t-il dépassé test_until_ms ? » Comparer directement les
        // deux valeurs serait faux de part et d'autre du débordement de
        // millis() ; on compare le signe de leur différence, ce qui reste
        // juste tant que l'écart est inférieur à 24 jours.
        const bool expired =
            static_cast<int32_t>(now_ms - test_until_ms) >= 0;
        if (expired) {
            test_active = false;
            motors::coast();
            return;
        }
        motors::applyDuty(test_duty);
        return;
    }

    const steering::WheelDuty duty = steering::mix(
        last_command.speed_pct, last_command.steering_pct, active_config);
    motors::applyDuty(duty);
}

}  // namespace

void setup() {
    Serial.begin(protocol::BAUD_RATE);

    // Couper les moteurs avant toute autre chose : au moment d'un reset, le
    // pont en H peut se retrouver dans un état indéterminé.
    motors::begin();
    sensors::begin();

    last_telemetry_ms = static_cast<uint32_t>(millis());
}

void loop() {
    const uint32_t now_ms = static_cast<uint32_t>(millis());

    sensors::update(now_ms);
    readSerial();

    const safety::Decision decision = arbitrate(now_ms);
    applyDecision(decision, now_ms);

    // Battement : renseigne le Raspberry Pi sur l'état courant même quand il
    // n'envoie plus rien, notamment sur la coupure par watchdog.
    if (now_ms - last_telemetry_ms >= HEARTBEAT_PERIOD_MS) {
        const char* error =
            decision.error != nullptr ? decision.error : last_error;
        sendTelemetry(has_received_command ? last_command.sequence : 0, error);
    }
}
