package com.smartcar.pilot.application.usecase

import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.model.CarSummary
import com.smartcar.pilot.domain.model.ControlMessage
import com.smartcar.pilot.domain.model.TelemetryFrame
import com.smartcar.pilot.domain.port.CarControlPort
import com.smartcar.pilot.domain.port.CarTelemetryPort
import com.smartcar.pilot.domain.port.GatewayPort
import com.smartcar.pilot.domain.port.VideoStreamPort
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals

/** Doublures de test pour les ports — pas de framework de mock, juste des implémentations minimales. */
private class FakeGateway(private val session: CarSession) : GatewayPort {
    override suspend fun listCars(): List<CarSummary> = listOf(CarSummary(session.carId, "test", true))
    override suspend fun claim(carId: String): CarSession = session
}

private class RecordingCarControlPort : CarControlPort {
    var opened: CarSession? = null
    val sent = mutableListOf<ControlMessage>()
    var closed = false

    override suspend fun open(session: CarSession) {
        opened = session
    }

    override suspend fun send(message: ControlMessage) {
        sent += message
    }

    override suspend fun close() {
        closed = true
    }
}

private class RecordingTelemetryPort : CarTelemetryPort {
    var opened: CarSession? = null
    var closed = false

    override suspend fun open(session: CarSession) {
        opened = session
    }

    override fun observe(): Flow<TelemetryFrame> = emptyFlow()

    override suspend fun close() {
        closed = true
    }
}

private class RecordingVideoPort : VideoStreamPort {
    var opened: CarSession? = null
    var closed = false

    override suspend fun open(session: CarSession) {
        opened = session
    }

    override fun observe(): Flow<ByteArray> = emptyFlow()

    override suspend fun close() {
        closed = true
    }
}

class ConnectToCarUseCaseTest {

    private val session = CarSession(
        carId = "car-01",
        ip = "192.168.4.23",
        controlPort = 5005,
        telemetryPort = 5006,
        videoPort = 5007,
        token = "token",
        expiresInS = 30,
        claimedAtMs = 0L,
    )

    @Test
    fun `claims the car then opens all three P2P channels with the returned session`() = runTest {
        val control = RecordingCarControlPort()
        val telemetry = RecordingTelemetryPort()
        val video = RecordingVideoPort()
        val useCase = ConnectToCarUseCase(FakeGateway(session), control, telemetry, video)

        val result = useCase("car-01")

        assertEquals(session, result)
        assertEquals(session, control.opened)
        assertEquals(session, telemetry.opened)
        assertEquals(session, video.opened)
    }
}
