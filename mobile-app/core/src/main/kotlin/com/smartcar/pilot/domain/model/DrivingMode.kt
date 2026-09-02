package com.smartcar.pilot.domain.model

/**
 * Mode de conduite (docs/mobile-app.md, §3 modèle d'états : IDLE -> AUTO/MANUAL,
 * toujours sous supervision d'une session pilote active). `EMERGENCY` reste
 * un [ConnectionState], pas une valeur de ce type — l'arrêt d'urgence
 * interrompt le flux de commandes, il ne « sélectionne » rien.
 */
enum class DrivingMode {
    AUTO,
    MANUAL,
}
