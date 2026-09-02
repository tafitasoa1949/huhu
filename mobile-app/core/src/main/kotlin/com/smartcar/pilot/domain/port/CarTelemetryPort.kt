package com.smartcar.pilot.domain.port

import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.model.TelemetryFrame
import kotlinx.coroutines.flow.Flow

/**
 * Port sortant (driven) du canal de télémétrie P2P — Phase 2
 * (docs/mobile-protocol.md). L'implémentation réelle (TCP) vit dans `app`.
 */
interface CarTelemetryPort {
    suspend fun open(session: CarSession)

    /** Une émission par trame reçue, au moins 5 Hz tant que la liaison tient. */
    fun observe(): Flow<TelemetryFrame>

    suspend fun close()
}
