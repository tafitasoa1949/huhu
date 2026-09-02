package com.smartcar.pilot.adapter.outbound.p2p

import com.smartcar.pilot.domain.model.DrivingMode
import com.smartcar.pilot.domain.model.TelemetryFrame
import com.smartcar.pilot.testsupport.FakeCar
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

/**
 * Canal de télémétrie TCP (docs/mobile-protocol.md, §Télémétrie) : flux de
 * lignes JSON, au moins 5 Hz. Les conditions simulées ici sont celles d'un
 * vrai flux réseau — trame partielle/mal formée au milieu, champs `null`
 * d'un capteur non câblé.
 */
class TcpCarTelemetryAdapterTest {

    private lateinit var car: FakeCar
    private lateinit var adapter: TcpCarTelemetryAdapter
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val received = LinkedBlockingQueue<TelemetryFrame>()

    @Before
    fun setUp() = runBlocking {
        car = FakeCar()
        adapter = TcpCarTelemetryAdapter()
        adapter.open(car.session())
        scope.launch { adapter.observe().collect { received.put(it) } }
        car.awaitTelemetryClient()
    }

    @After
    fun tearDown() = runBlocking {
        scope.cancel()
        adapter.close()
        car.close()
    }

    @Test
    fun `une trame complete est decodee champ par champ`() {
        car.pushTelemetry(
            """{"type":"telemetry","seq":812,"ts_ms":1699999999100,"speed_pct":40,""" +
                """"steering_pct":-15,"battery_pct":76,"rssi_dbm":-58,"mode":"MANUAL"}""",
        )

        val frame = nextFrame()
        assertEquals(812, frame.sequence)
        assertEquals(1699999999100L, frame.tsMs)
        assertEquals(40, frame.speedPct)
        assertEquals(-15, frame.steeringPct)
        assertEquals(76, frame.batteryPct)
        assertEquals(-58, frame.rssiDbm)
        assertEquals(DrivingMode.MANUAL, frame.mode)
    }

    @Test
    fun `une valeur non mesurable reste null, jamais zero`() {
        car.pushTelemetry(
            """{"type":"telemetry","seq":1,"ts_ms":1,"speed_pct":0,"steering_pct":0,""" +
                """"battery_pct":null,"rssi_dbm":null,"mode":null}""",
        )

        val frame = nextFrame()
        assertNull(frame.batteryPct)
        assertNull(frame.rssiDbm)
        // Mode absent : l'app garde la dernière valeur qu'elle connaît, elle
        // ne doit surtout pas retomber sur MANUAL par défaut.
        assertNull(frame.mode)
    }

    @Test
    fun `une ligne mal formee est ignoree sans couper le flux`() {
        car.pushTelemetry("""{"type":"telemetry","seq":1,"ts_ms":""")
        car.pushTelemetry("""{"type":"telemetry","seq":2,"ts_ms":2,"speed_pct":10,"steering_pct":0,""" +
            """"battery_pct":null,"rssi_dbm":null,"mode":"AUTO"}""")

        val frame = nextFrame()
        assertEquals("la trame valide qui suit doit passer", 2, frame.sequence)
        assertEquals(DrivingMode.AUTO, frame.mode)
    }

    private fun nextFrame(): TelemetryFrame {
        val frame = received.poll(5, TimeUnit.SECONDS)
        assertNotNull("aucune trame de télémétrie décodée", frame)
        return frame!!
    }
}
