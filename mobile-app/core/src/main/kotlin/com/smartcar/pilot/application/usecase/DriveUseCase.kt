package com.smartcar.pilot.application.usecase

import com.smartcar.pilot.application.control.JoystickMapper
import com.smartcar.pilot.application.control.SequenceCounter
import com.smartcar.pilot.domain.model.ControlMessage
import com.smartcar.pilot.domain.port.CarControlPort

/**
 * Un tick du flux de pilotage continu à 20 Hz (docs/mobile-protocol.md,
 * PDF §Phase 3) : position brute du joystick -> `ControlMessage.Drive`.
 * Appelé même joystick centré, c'est ce flux régulier qui maintient la
 * liaison — voir `application.session.CarPilotSession`.
 */
class DriveUseCase(private val control: CarControlPort) {
    suspend operator fun invoke(sequence: SequenceCounter, throttleAxis: Float, steeringAxis: Float) {
        control.send(
            ControlMessage.Drive(
                sequence = sequence.next(),
                tsMs = System.currentTimeMillis(),
                speedPct = JoystickMapper.speedPct(throttleAxis),
                steeringPct = JoystickMapper.steeringPct(steeringAxis),
            )
        )
    }
}
