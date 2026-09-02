package com.smartcar.pilot.application.watchdog

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ConnectionWatchdogTest {

    private val watchdog = ConnectionWatchdog(timeoutMs = 2000L)

    @Test
    fun `link is not lost right after a frame`() {
        assertFalse(watchdog.isLinkLost(lastFrameAtMs = 1000L, nowMs = 1000L))
    }

    @Test
    fun `link is not lost just under the timeout`() {
        assertFalse(watchdog.isLinkLost(lastFrameAtMs = 1000L, nowMs = 2999L))
    }

    @Test
    fun `link is lost past the 2 second timeout`() {
        assertTrue(watchdog.isLinkLost(lastFrameAtMs = 1000L, nowMs = 3001L))
    }
}
