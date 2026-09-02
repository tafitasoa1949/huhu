package com.smartcar.pilot.domain.model

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CarSessionTest {

    private val session = CarSession(
        carId = "car-01",
        ip = "192.168.4.23",
        controlPort = 5005,
        telemetryPort = 5006,
        videoPort = 5007,
        token = "token",
        expiresInS = 30,
        claimedAtMs = 10_000L,
    )

    @Test
    fun `not expired before expiresInS has elapsed`() {
        assertFalse(session.isExpired(nowMs = 10_000L + 29_000L))
    }

    @Test
    fun `expired once expiresInS has elapsed`() {
        assertTrue(session.isExpired(nowMs = 10_000L + 31_000L))
    }
}
