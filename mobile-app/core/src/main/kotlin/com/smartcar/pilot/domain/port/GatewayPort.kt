package com.smartcar.pilot.domain.port

import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.model.CarSummary

/**
 * Port sortant (driven) vers le serveur Gateway — Phase 1 uniquement
 * (docs/mobile-protocol.md). Aucune implémentation ici : `core` ignore tout
 * détail de transport (REST, ou autre chose demain), seule compte
 * l'intention métier.
 */
interface GatewayPort {
    /** `GET /api/cars`. */
    suspend fun listCars(): List<CarSummary>

    /** `POST /api/cars/{carId}/claim`. Lève [com.smartcar.pilot.domain.model.CarAlreadyClaimedException] si refusé. */
    suspend fun claim(carId: String): CarSession
}
