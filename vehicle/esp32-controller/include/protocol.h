#pragma once

#include <stddef.h>
#include <stdint.h>

// Constantes et structures du protocole série Raspberry Pi <-> ESP32.
//
// Ce fichier ne dépend ni d'Arduino ni du matériel : il est compilable en
// natif, ce qui permet de tester le protocole sur PC sans carte ESP32.
// Référence : section 5 du plan de développement.

namespace protocol {

// Liaison série, section 5.1.
constexpr unsigned long BAUD_RATE = 115200;

// Silence maximal toléré avant arrêt automatique, section 5.5.
//
// Les durées sont en uint32_t et non en unsigned long : c'est la largeur de
// millis() sur l'ESP32, alors qu'un unsigned long fait 64 bits sur un PC.
// Fixer la largeur garantit que le débordement du compteur se comporte de
// façon identique sur la carte et dans les tests natifs.
constexpr uint32_t COMMAND_TIMEOUT_MS = 500;

// Longueur maximale d'une ligne JSON acceptée en entrée. Une commande DRIVE
// complète fait environ 80 octets ; 192 laisse de la marge tout en bornant la
// mémoire consommée par une ligne malformée.
constexpr size_t MAX_LINE_LENGTH = 192;

// Taille du tampon de sortie pour une ligne TELEMETRY.
constexpr size_t MAX_TELEMETRY_LENGTH = 256;

// Bornes officielles des champs de commande, section 4.1.
constexpr int SPEED_MIN_PCT = 0;
constexpr int SPEED_MAX_PCT = 100;
constexpr int STEERING_MIN_PCT = -100;
constexpr int STEERING_MAX_PCT = 100;

// Durée maximale d'un essai moteur, en millisecondes.
//
// Un essai de calibration se fait roues levées, à la main, en regardant la
// roue tourner. Une durée bornée garantit que la roue s'arrête même si le
// Raspberry Pi cesse d'émettre au mauvais moment, et empêche de transformer
// l'outil de calibration en pilotage détourné.
constexpr uint32_t TEST_MAX_DURATION_MS = 3000;

// Rapport cyclique maximal accepté pour un essai moteur. Volontairement bas :
// la calibration cherche un seuil de démarrage, pas de la vitesse.
constexpr int TEST_MAX_DUTY_PCT = 60;

// Résultat de l'analyse d'une ligne reçue.
//
// Toute valeur différente de Ok impose l'arrêt des moteurs et l'émission d'une
// télémétrie en statut ERROR (section 5.5 : « JSON invalide -> l'ESP32
// n'applique pas la commande et retourne une erreur »).
enum class ParseStatus {
    Ok,
    EmptyLine,
    InvalidJson,
    UnknownType,
    MissingField,
    InvalidSpeed,
    InvalidSteering,
    InvalidConfig,
    InvalidTarget,
    InvalidDuty,
    InvalidDuration,
};

// Nature de la ligne reçue.
enum class MessageType {
    Drive,
    Config,
    Test,
};

// Commande DRIVE décodée, section 5.2.
struct DriveMessage {
    long sequence;
    int speed_pct;
    int steering_pct;
    bool emergency;
};

// Réglage de calibration appliqué à chaud.
//
// Tous les champs sont facultatifs : une ligne CONFIG ne modifie que ce
// qu'elle mentionne. Cela permet de corriger une seule valeur — l'inversion
// d'un moteur, par exemple — sans avoir à renvoyer tout le profil et risquer
// d'écraser un réglage trouvé dix secondes plus tôt.
struct ConfigMessage {
    long sequence;

    bool has_steering_gain;
    int steering_gain_pct;

    bool has_min_duty;
    int min_duty_pct;

    bool has_max_duty;
    int max_duty_pct;

    bool has_invert_left;
    bool invert_left;

    bool has_invert_right;
    bool invert_right;
};

// Cible d'un essai moteur.
enum class TestTarget {
    Left,
    Right,
    Both,
};

// Essai moteur : pilote un côté directement, sans passer par le mélange
// différentiel. C'est indispensable pour vérifier le sens de rotation moteur
// par moteur, ce qu'une commande DRIVE ne permet pas puisqu'elle agit
// forcément sur les deux côtés à la fois.
struct TestMessage {
    long sequence;
    TestTarget target;
    int duty_pct;  // signé : négatif = marche arrière
    uint32_t duration_ms;
};

// Ligne décodée, quelle que soit sa nature.
struct ParsedMessage {
    MessageType type;
    DriveMessage drive;
    ConfigMessage config;
    TestMessage test;
};

// Télémétrie à renvoyer, section 5.3.
//
// Les champs optionnels du contrat sont exprimés par un couple
// « valeur + drapeau de présence » : un drapeau à false est sérialisé en
// null, ce qui est la représentation attendue par le Raspberry Pi.
struct TelemetryMessage {
    long sequence;
    const char* status;  // "OK" ou "ERROR"
    const char* error;   // nullptr si aucune erreur

    bool has_obstacle_distance;
    float obstacle_distance_m;

    bool has_battery;
    int battery_pct;

    bool has_rpm;
    float left_rpm;
    float right_rpm;
};

// Codes d'erreur transmis dans le champ `error` de la télémétrie.
constexpr const char* ERROR_INVALID_JSON = "INVALID_JSON";
constexpr const char* ERROR_UNKNOWN_TYPE = "UNKNOWN_TYPE";
constexpr const char* ERROR_MISSING_FIELD = "MISSING_FIELD";
constexpr const char* ERROR_INVALID_SPEED = "INVALID_SPEED";
constexpr const char* ERROR_INVALID_STEERING = "INVALID_STEERING";
constexpr const char* ERROR_INVALID_CONFIG = "INVALID_CONFIG";
constexpr const char* ERROR_INVALID_TARGET = "INVALID_TARGET";
constexpr const char* ERROR_INVALID_DUTY = "INVALID_DUTY";
constexpr const char* ERROR_INVALID_DURATION = "INVALID_DURATION";
constexpr const char* ERROR_LINE_TOO_LONG = "LINE_TOO_LONG";
constexpr const char* ERROR_COMMAND_TIMEOUT = "COMMAND_TIMEOUT";
constexpr const char* ERROR_EMERGENCY_STOP = "EMERGENCY_STOP";
constexpr const char* ERROR_LOCAL_OBSTACLE = "LOCAL_OBSTACLE";

// Statuts.
constexpr const char* STATUS_OK = "OK";
constexpr const char* STATUS_ERROR = "ERROR";

// Traduit un ParseStatus en code d'erreur du protocole.
// Renvoie nullptr pour ParseStatus::Ok.
const char* errorCodeFor(ParseStatus status);

}  // namespace protocol
