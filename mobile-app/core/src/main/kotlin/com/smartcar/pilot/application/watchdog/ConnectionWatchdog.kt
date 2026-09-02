package com.smartcar.pilot.application.watchdog

/**
 * Détecte une perte de liaison P2P côté app : plus aucune trame de
 * télémétrie depuis plus de [timeoutMs] (docs/mobile-protocol.md, règle de
 * sécurité NFR — 2 s). Fonction pure du temps ; c'est l'appelant qui décide
 * quand la réévaluer (voir `application.session.CarPilotSession`).
 */
class ConnectionWatchdog(private val timeoutMs: Long = DEFAULT_TIMEOUT_MS) {

    fun isLinkLost(lastFrameAtMs: Long, nowMs: Long): Boolean =
        nowMs - lastFrameAtMs > timeoutMs

    companion object {
        const val DEFAULT_TIMEOUT_MS = 2000L
    }
}
