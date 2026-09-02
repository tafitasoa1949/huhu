package com.smartcar.pilot.application.usecase

import com.smartcar.pilot.domain.port.CarControlPort
import com.smartcar.pilot.domain.port.CarTelemetryPort
import com.smartcar.pilot.domain.port.VideoStreamPort

/** Fin de session volontaire (écran de conduite quitté) : referme les trois canaux P2P. */
class DisconnectUseCase(
    private val control: CarControlPort,
    private val telemetry: CarTelemetryPort,
    private val video: VideoStreamPort,
) {
    suspend operator fun invoke() {
        control.close()
        telemetry.close()
        video.close()
    }
}
