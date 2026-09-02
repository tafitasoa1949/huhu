package com.smartcar.pilot.application.usecase

import com.smartcar.pilot.application.control.SequenceCounter
import com.smartcar.pilot.domain.model.ControlMessage
import com.smartcar.pilot.domain.port.CarControlPort

/** Bouton d'arrêt d'urgence, toujours accessible depuis l'écran de conduite (PDF §Phase 2). */
class EmergencyStopUseCase(private val control: CarControlPort) {
    suspend operator fun invoke(sequence: SequenceCounter) {
        control.send(ControlMessage.Emergency(sequence = sequence.next(), tsMs = System.currentTimeMillis()))
    }
}
