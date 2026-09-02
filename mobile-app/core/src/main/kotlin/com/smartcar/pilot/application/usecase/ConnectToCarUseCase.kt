package com.smartcar.pilot.application.usecase

import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.port.CarControlPort
import com.smartcar.pilot.domain.port.CarTelemetryPort
import com.smartcar.pilot.domain.port.GatewayPort
import com.smartcar.pilot.domain.port.VideoStreamPort

/**
 * Bascule Phase 1 -> Phase 2 (docs/mobile-protocol.md) : revendique la
 * voiture auprès du Gateway, puis ouvre les trois canaux P2P (contrôle,
 * télémétrie, vidéo) avec le jeton obtenu. Le Gateway n'est plus sollicité
 * après cet appel.
 */
class ConnectToCarUseCase(
    private val gateway: GatewayPort,
    private val control: CarControlPort,
    private val telemetry: CarTelemetryPort,
    private val video: VideoStreamPort,
) {
    suspend operator fun invoke(carId: String): CarSession {
        val session = gateway.claim(carId)
        control.open(session)
        telemetry.open(session)
        video.open(session)
        return session
    }
}
