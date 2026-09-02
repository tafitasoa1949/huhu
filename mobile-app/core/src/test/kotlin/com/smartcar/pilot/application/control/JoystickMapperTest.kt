package com.smartcar.pilot.application.control

import kotlin.test.Test
import kotlin.test.assertEquals

class JoystickMapperTest {

    @Test
    fun `full throttle forward gives 100 percent speed`() {
        assertEquals(100, JoystickMapper.speedPct(1f))
    }

    @Test
    fun `centered throttle gives zero speed`() {
        assertEquals(0, JoystickMapper.speedPct(0f))
    }

    @Test
    fun `pulling the throttle stick back gives reverse speed, per VH-02`() {
        assertEquals(-100, JoystickMapper.speedPct(-1f))
        assertEquals(-50, JoystickMapper.speedPct(-0.5f))
    }

    @Test
    fun `steering left is negative, matching the shared convention`() {
        assertEquals(-100, JoystickMapper.steeringPct(-1f))
        assertEquals(100, JoystickMapper.steeringPct(1f))
        assertEquals(0, JoystickMapper.steeringPct(0f))
    }

    @Test
    fun `axis values beyond the pad are clamped, not rejected`() {
        assertEquals(100, JoystickMapper.speedPct(5f))
        assertEquals(-100, JoystickMapper.speedPct(-5f))
        assertEquals(-100, JoystickMapper.steeringPct(-5f))
    }
}

class SequenceCounterTest {

    @Test
    fun `starts at one and increments strictly`() {
        val counter = SequenceCounter()
        assertEquals(1, counter.next())
        assertEquals(2, counter.next())
        assertEquals(3, counter.next())
    }
}
