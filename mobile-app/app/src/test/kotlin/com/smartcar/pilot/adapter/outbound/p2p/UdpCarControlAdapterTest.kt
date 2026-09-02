package com.smartcar.pilot.adapter.outbound.p2p

import com.smartcar.pilot.domain.model.ControlMessage
import com.smartcar.pilot.domain.model.DrivingMode
import com.smartcar.pilot.testsupport.FakeCar
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

/**
 * Canal de contrôle UDP (docs/mobile-protocol.md, §Commandes) vu depuis la
 * voiture : ce sont exactement les champs que `network/p2p_server.py` exige
 * pour ne pas rejeter le paquet — un nom de champ qui dérive ici, et la
 * voiture ignore silencieusement toutes les commandes.
 */
class UdpCarControlAdapterTest {

    private lateinit var car: FakeCar
    private lateinit var adapter: UdpCarControlAdapter

    @Before
    fun setUp() = runBlocking {
        car = FakeCar()
        adapter = UdpCarControlAdapter()
        adapter.open(car.session())
    }

    @After
    fun tearDown() = runBlocking {
        adapter.close()
        car.close()
    }

    @Test
    fun `un paquet drive porte le jeton, la sequence, l horodatage et les pourcentages`() = runBlocking {
        adapter.send(
            ControlMessage.Drive(sequence = 7, tsMs = 1_700_000_000_000L, speedPct = 42, steeringPct = -15),
        )

        val packet = nextPacket()
        assertEquals("drive", packet.text("type"))
        assertEquals(car.token, packet.text("token"))
        assertEquals(7, packet.int("seq"))
        assertEquals(1_700_000_000_000L, packet.long("ts_ms"))
        assertEquals(42, packet.int("speed_pct"))
        assertEquals(-15, packet.int("steering_pct"))
    }

    @Test
    fun `un arret d urgence part avec son propre numero de sequence`() = runBlocking {
        adapter.send(ControlMessage.Emergency(sequence = 8, tsMs = 1_700_000_000_050L))

        val packet = nextPacket()
        assertEquals("emergency", packet.text("type"))
        assertEquals(car.token, packet.text("token"))
        assertEquals(8, packet.int("seq"))
    }

    @Test
    fun `une bascule de mode transmet AUTO ou MANUAL tel quel`() = runBlocking {
        adapter.send(ControlMessage.SetMode(sequence = 9, tsMs = 1L, mode = DrivingMode.AUTO))

        val packet = nextPacket()
        assertEquals("mode", packet.text("type"))
        assertEquals("AUTO", packet.text("mode"))
    }

    @Test
    fun `apres fermeture, plus rien n est emis vers la voiture`() = runBlocking {
        adapter.close()
        adapter.send(ControlMessage.Drive(sequence = 1, tsMs = 1L, speedPct = 100, steeringPct = 0))

        // Canal fermé : l'envoi est un non-événement, pas une exception —
        // l'écran de conduite continue d'émettre à 20 Hz pendant qu'on quitte.
        assertNull(car.receiveControlPacket(timeoutMs = 300))
    }

    private fun nextPacket(): JsonObject {
        val raw = car.receiveControlPacket()
        assertNotNull("aucun paquet UDP reçu par la voiture", raw)
        return Json.parseToJsonElement(raw!!).jsonObject
    }

    private fun JsonObject.text(field: String): String = getValue(field).jsonPrimitive.content
    private fun JsonObject.int(field: String): Int = getValue(field).jsonPrimitive.int
    private fun JsonObject.long(field: String): Long = getValue(field).jsonPrimitive.long
}
