package com.smartcar.pilot.domain.model

/**
 * Trame reçue sur le canal de télémétrie TCP (docs/mobile-protocol.md,
 * Phase 2), au moins 5 fois par seconde. Une valeur absente vaut `null`,
 * jamais 0 (docs/contracts.md, convention "valeur inconnue").
 */
data class TelemetryFrame(
    val sequence: Int,
    val tsMs: Long,
    val speedPct: Int?,
    val steeringPct: Int?,
    val batteryPct: Int?,
    val rssiDbm: Int?,
    val mode: DrivingMode?,
)
