package com.smartcar.pilot.domain.model

/** État de la session de pilotage, du point de vue de l'app. */
sealed interface ConnectionState {
    /** Avant toute action : ni découverte, ni association. */
    data object Idle : ConnectionState

    /** `GET /api/cars` en cours (Phase 1). */
    data object Discovering : ConnectionState

    /** `POST /api/cars/{id}/claim` en cours, puis ouverture des canaux P2P (Phase 1 -> 2). */
    data object Associating : ConnectionState

    /** Canaux P2P ouverts, télémétrie reçue récemment. */
    data object Connected : ConnectionState

    /**
     * Plus aucune trame de télémétrie depuis plus de 2 s (voir
     * `application.watchdog.ConnectionWatchdog`) : la voiture a probablement
     * déjà coupé les moteurs de son côté (docs/mobile-protocol.md). L'app
     * continue de tenter d'émettre, en vue d'une reconnexion automatique.
     */
    data object LinkLost : ConnectionState

    /** Déconnexion volontaire — écran de conduite quitté normalement. */
    data object Disconnected : ConnectionState

    /** Échec d'association ou de découverte (Gateway injoignable, voiture déjà revendiquée...). */
    data class Failed(val reason: String) : ConnectionState
}
