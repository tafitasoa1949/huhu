#pragma once

#include <stdint.h>

// Arbitrage de sécurité local de l'ESP32.
//
// Rassemble en un seul endroit toutes les raisons de couper les moteurs :
// watchdog de communication, arrêt d'urgence demandé par le Raspberry Pi,
// bouton physique, obstacle vu par le capteur local et dernière ligne série
// rejetée. Tickets ESP-09 et ESP-10, règles de la section 5.5 du plan.
//
// Le module est une fonction pure : l'heure courante et l'état des entrées
// sont passés en paramètres plutôt que lus depuis millis() ou les broches.
// Il est donc testable en natif sur PC, y compris le débordement du compteur
// de millisecondes.

namespace safety {

// État courant de l'arbitrage, du plus prioritaire au moins prioritaire.
enum class State {
    ButtonPressed,      // bouton d'arrêt d'urgence physique enfoncé
    EmergencyCommand,   // emergency = true reçu du Raspberry Pi
    LocalObstacle,      // capteur local sous la distance critique
    ProtocolError,      // dernière ligne reçue rejetée
    WaitingForCommand,  // aucune commande reçue depuis le démarrage
    CommunicationLost,  // silence supérieur au délai autorisé
    Active,             // conduite autorisée
};

// Entrées de l'arbitrage.
struct Inputs {
    // Heure courante, en millisecondes monotoniques (millis()).
    uint32_t now_ms;

    // Délai de silence au-delà duquel les moteurs sont coupés.
    uint32_t timeout_ms;

    // Faux tant qu'aucune commande valide n'a été reçue depuis le démarrage.
    bool has_received_command;

    // Date de la dernière commande valide.
    uint32_t last_command_ms;

    // Champ `emergency` de la dernière commande valide.
    bool commanded_emergency;

    // Vrai si la dernière ligne reçue a été rejetée. Reste vrai jusqu'à la
    // prochaine commande valide : une erreur de protocole ne doit pas être
    // effacée par le simple passage du temps.
    bool last_line_rejected;

    // Bouton d'arrêt d'urgence physique, déjà débruité par l'appelant.
    bool button_pressed;

    // Mesure du télémètre local. `has_local_distance` est faux si le capteur
    // est absent, désactivé ou n'a pas encore produit de mesure fiable.
    bool has_local_distance;
    float local_distance_m;
    float critical_distance_m;
};

// Verdict de l'arbitrage.
struct Decision {
    // Faux impose la coupure immédiate des moteurs.
    bool motors_allowed;

    State state;

    // Code d'erreur du protocole à remonter dans la télémétrie, ou nullptr
    // si l'état ne constitue pas une erreur.
    const char* error;
};

// Applique les règles de sécurité dans l'ordre de priorité.
Decision evaluate(const Inputs& inputs);

// Nom lisible d'un état, pour les traces série.
const char* stateName(State state);

}  // namespace safety
