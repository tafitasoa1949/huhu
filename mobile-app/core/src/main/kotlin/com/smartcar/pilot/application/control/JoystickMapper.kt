package com.smartcar.pilot.application.control

import kotlin.math.roundToInt

/**
 * Convertit la position d'un joystick (axe -1.0 à +1.0) en `speed_pct` /
 * `steering_pct` conformes à docs/mobile-protocol.md : contrairement au
 * contrat de conduite autonome (docs/contracts.md, `speed_pct` ∈ [0, 100]),
 * le pilotage manuel direct autorise la marche arrière — VH-02, PDF §Phase 3.
 */
object JoystickMapper {

    fun speedPct(throttleAxis: Float): Int =
        (throttleAxis.coerceIn(-1f, 1f) * 100f).roundToInt().coerceIn(-100, 100)

    fun steeringPct(steeringAxis: Float): Int =
        (steeringAxis.coerceIn(-1f, 1f) * 100f).roundToInt().coerceIn(-100, 100)
}

/** Compteur de séquence croissant, propre à une session de pilotage. */
class SequenceCounter {
    private var value = 0

    fun next(): Int {
        value += 1
        return value
    }
}
