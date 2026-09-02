package com.smartcar.pilot.application.usecase

import com.smartcar.pilot.application.control.SequenceCounter
import com.smartcar.pilot.domain.model.ControlMessage
import com.smartcar.pilot.domain.model.DrivingMode
import com.smartcar.pilot.domain.port.CarControlPort

/** Bascule AUTO/MANUAL, accessible depuis l'écran de conduite (docs/mobile-app.md, §3). */
class SetModeUseCase(private val control: CarControlPort) {
    suspend operator fun invoke(sequence: SequenceCounter, mode: DrivingMode) {
        control.send(ControlMessage.SetMode(sequence = sequence.next(), tsMs = System.currentTimeMillis(), mode = mode))
    }
}
