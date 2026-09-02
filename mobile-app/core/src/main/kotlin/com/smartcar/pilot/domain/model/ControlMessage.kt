package com.smartcar.pilot.domain.model

/**
 * Paquets envoyés par l'app sur le canal de contrôle UDP
 * (docs/mobile-protocol.md, Phase 2). `sequence`/`tsMs` existent sur les
 * deux variantes : la voiture ignore tout paquet dont `sequence` n'est pas
 * strictement croissant, ou dont `tsMs` est trop ancien.
 */
sealed interface ControlMessage {
    val sequence: Int
    val tsMs: Long

    /**
     * Envoyé en continu à 20 Hz tant que la session est ouverte, y compris
     * joystick au centre — c'est ce flux régulier qui tient lieu de maintien
     * de liaison, pas un message dédié.
     */
    data class Drive(
        override val sequence: Int,
        override val tsMs: Long,
        val speedPct: Int,
        val steeringPct: Int,
    ) : ControlMessage

    /** Interrompt le flux régulier pour un arrêt immédiat, sans attendre le prochain tick. */
    data class Emergency(
        override val sequence: Int,
        override val tsMs: Long,
    ) : ControlMessage

    /**
     * Demande de bascule AUTO/MANUAL (docs/mobile-app.md, §3). Une demande,
     * pas une garantie : c'est la trame de télémétrie qui dit ce que la
     * voiture applique réellement, même principe que `speedPct`/`steeringPct`.
     */
    data class SetMode(
        override val sequence: Int,
        override val tsMs: Long,
        val mode: DrivingMode,
    ) : ControlMessage
}
