package com.smartcar.pilot.domain.model

/**
 * Résultat d'une association réussie auprès du Gateway (docs/mobile-protocol.md,
 * Phase 1) : tout ce qu'il faut pour parler directement à la voiture en P2P
 * (Phase 2), sans plus jamais repasser par le Gateway.
 */
data class CarSession(
    val carId: String,
    val ip: String,
    val controlPort: Int,
    val telemetryPort: Int,
    // Relais MJPEG brut du Raspberry Pi (docs/mobile-protocol.md, §Phase 2 —
    // Flux vidéo) : le Pi 5 n'a pas d'encodeur H.264 matériel, la vidéo
    // ESP32-CAM est donc reproxyfiée telle quelle, sans réencodage. Le
    // téléphone ne parle jamais directement à l'ESP32-CAM.
    val videoPort: Int,
    val token: String,
    val expiresInS: Int,
    val claimedAtMs: Long,
) {
    fun isExpired(nowMs: Long): Boolean = nowMs - claimedAtMs > expiresInS * 1000L
}
