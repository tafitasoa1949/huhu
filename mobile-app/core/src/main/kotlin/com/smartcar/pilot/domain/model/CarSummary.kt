package com.smartcar.pilot.domain.model

/** Une voiture connue du Gateway, avant toute association (docs/mobile-protocol.md, Phase 1). */
data class CarSummary(
    val carId: String,
    val name: String,
    val online: Boolean,
)
