package com.smartcar.pilot.application.usecase

import com.smartcar.pilot.application.control.SequenceCounter
import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.model.ControlMessage
import com.smartcar.pilot.domain.model.DrivingMode
import com.smartcar.pilot.domain.port.CarControlPort
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

private class RecordingControlPort : CarControlPort {
    val sent = mutableListOf<ControlMessage>()
    override suspend fun open(session: CarSession) = Unit
    override suspend fun send(message: ControlMessage) { sent += message }
    override suspend fun close() = Unit
}

class DriveUseCaseTest {

    @Test
    fun `maps joystick axes to a Drive message with an increasing sequence`() = runTest {
        val control = RecordingControlPort()
        val useCase = DriveUseCase(control)
        val sequence = SequenceCounter()

        useCase(sequence, throttleAxis = 1f, steeringAxis = -0.5f)
        useCase(sequence, throttleAxis = 0f, steeringAxis = 0f)

        assertEquals(2, control.sent.size)
        val first = assertIs<ControlMessage.Drive>(control.sent[0])
        assertEquals(1, first.sequence)
        assertEquals(100, first.speedPct)
        assertEquals(-50, first.steeringPct)

        val second = assertIs<ControlMessage.Drive>(control.sent[1])
        assertEquals(2, second.sequence)
        assertEquals(0, second.speedPct)
    }
}

class EmergencyStopUseCaseTest {

    @Test
    fun `sends an Emergency message`() = runTest {
        val control = RecordingControlPort()
        val useCase = EmergencyStopUseCase(control)

        useCase(SequenceCounter())

        assertEquals(1, control.sent.size)
        assertIs<ControlMessage.Emergency>(control.sent.single())
    }
}

class SetModeUseCaseTest {

    @Test
    fun `sends a SetMode message with the requested mode`() = runTest {
        val control = RecordingControlPort()
        val useCase = SetModeUseCase(control)

        useCase(SequenceCounter(), DrivingMode.AUTO)

        val sent = assertIs<ControlMessage.SetMode>(control.sent.single())
        assertEquals(DrivingMode.AUTO, sent.mode)
    }
}
