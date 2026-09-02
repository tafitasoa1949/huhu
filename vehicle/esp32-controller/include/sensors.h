#pragma once

#include <stdint.h>

// Entrées locales de l'ESP32 : bouton d'arrêt d'urgence, télémètre à
// ultrasons, encodeurs de roue et tension batterie. Tickets ESP-10 (arrêt
// local) et section 5.3 du plan (champs de télémétrie).
//
// Chaque capteur est activé séparément dans pin_config.h et désactivé par
// défaut. Sur une carte ESP32 nue, toutes les lectures renvoient « valeur
// absente », ce qui se traduit par `null` dans la télémétrie : le contrat
// reste respecté sans qu'aucun périphérique ne soit branché.

namespace sensors {

// Mesure optionnelle. `valid` à faux signifie « inconnu », pas « zéro ».
struct Reading {
    bool valid;
    float value;
};

// Configure les broches des capteurs activés.
void begin();

// À appeler à chaque tour de boucle. Déclenche les mesures qui doivent l'être
// périodiquement (le télémètre à ultrasons, notamment, ne peut pas être
// interrogé à chaque itération sans saturer la boucle).
void update(uint32_t now_ms);

// Bouton d'arrêt d'urgence, débruité. Faux si le bouton n'est pas activé
// dans la configuration.
bool emergencyButtonPressed();

// Dernière distance mesurée par le télémètre local, en mètres.
Reading obstacleDistanceM();

// Régime des roues, en tours par minute.
Reading leftRpm();
Reading rightRpm();

// Charge estimée de la batterie, en pourcentage de la plage utile.
Reading batteryPct();

}  // namespace sensors
