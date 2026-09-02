package com.smartcar.pilot.application.usecase

import com.smartcar.pilot.domain.model.CarSummary
import com.smartcar.pilot.domain.port.GatewayPort

/** Phase 1 (docs/mobile-protocol.md) : liste des voitures joignables via le Gateway. */
class DiscoverCarsUseCase(private val gateway: GatewayPort) {
    suspend operator fun invoke(): List<CarSummary> = gateway.listCars()
}
