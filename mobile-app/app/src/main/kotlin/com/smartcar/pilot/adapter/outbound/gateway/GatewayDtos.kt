package com.smartcar.pilot.adapter.outbound.gateway

import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.model.CarSummary
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Corps JSON du Gateway (docs/mobile-protocol.md, Phase 1). Noms de champs imposés côté fil. */
@Serializable
data class CarSummaryDto(
    @SerialName("car_id") val carId: String,
    val name: String,
    val online: Boolean,
) {
    fun toDomain() = CarSummary(carId = carId, name = name, online = online)
}

@Serializable
data class ClaimResponseDto(
    @SerialName("car_id") val carId: String,
    val ip: String,
    @SerialName("control_port") val controlPort: Int,
    @SerialName("telemetry_port") val telemetryPort: Int,
    // Port du relais MJPEG brut servi par le Raspberry Pi (docs/mobile-protocol.md,
    // §Phase 2 — Flux vidéo) — pas celui de l'ESP32-CAM, jamais exposé au téléphone.
    @SerialName("video_port") val videoPort: Int,
    val token: String,
    @SerialName("expires_in_s") val expiresInS: Int,
) {
    fun toDomain(claimedAtMs: Long) = CarSession(
        carId = carId,
        ip = ip,
        controlPort = controlPort,
        telemetryPort = telemetryPort,
        videoPort = videoPort,
        token = token,
        expiresInS = expiresInS,
        claimedAtMs = claimedAtMs,
    )
}
