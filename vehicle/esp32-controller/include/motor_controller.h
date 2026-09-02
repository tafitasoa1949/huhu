#pragma once

#include "steering_controller.h"

// Couche matérielle des moteurs : pont en H L298N piloté par le périphérique
// LEDC de l'ESP32. Ticket ESP-07.
//
// C'est le seul module qui touche réellement aux broches. Tout le calcul des
// consignes est fait en amont par steering_controller, qui lui ne dépend pas
// du matériel. Conséquence pratique : ce fichier est le seul à devoir être
// revu si le driver change (TB6612FNG, DRV8833...), et le seul qui ne puisse
// pas être testé sans carte.

namespace motors {

// Configure les broches et les canaux PWM, puis coupe les moteurs.
// À appeler une fois depuis setup(), avant tout autre appel.
void begin();

// Applique une consigne par roue, en pourcentage signé.
// Négatif = marche arrière. Les valeurs sont ramenées dans [-100, 100].
void applyDuty(const steering::WheelDuty& duty);

// Arrêt en roue libre : le pont est désactivé, la voiture s'arrête par
// frottement. C'est l'arrêt par défaut, le moins brutal pour la mécanique.
void coast();

// Arrêt actif : les deux bornes du moteur sont mises au même potentiel, ce
// qui freine par court-circuit de la force contre-électromotrice. Réservé aux
// arrêts d'urgence, où la distance d'arrêt prime sur la douceur.
void brake();

}  // namespace motors
