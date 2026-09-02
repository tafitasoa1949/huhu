package com.smartcar.pilot.adapter.outbound.gateway

import com.smartcar.pilot.domain.model.CarAlreadyClaimedException
import com.smartcar.pilot.domain.model.CarSummary
import com.smartcar.pilot.domain.model.GatewayUnreachableException
import com.smartcar.pilot.testsupport.FakeCar
import java.net.ServerSocket
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test

/**
 * Phase 1 (docs/mobile-protocol.md) contre un vrai serveur HTTP : les noms
 * de champs `car_id`, `control_port`... sont imposés côté fil par le Gateway
 * (`gateway/src/smart_car_gateway/app.py`), ce test est ce qui les tient.
 */
class GatewayHttpAdapterTest {

    private lateinit var car: FakeCar
    private lateinit var adapter: GatewayHttpAdapter

    @Before
    fun setUp() {
        car = FakeCar()
        adapter = GatewayHttpAdapter()
        adapter.configure(car.host, car.gatewayPort)
    }

    @After
    fun tearDown() {
        car.close()
    }

    @Test
    fun `la liste des voitures est mappee depuis le JSON du Gateway`() = runBlocking {
        assertEquals(
            listOf(CarSummary(carId = "car-01", name = "Voiture de test", online = true)),
            adapter.listCars(),
        )
    }

    @Test
    fun `un claim accepte renvoie de quoi ouvrir les trois canaux P2P`() = runBlocking {
        val session = adapter.claim("car-01")

        assertEquals("car-01", session.carId)
        assertEquals(car.host, session.ip)
        assertEquals(car.controlPort, session.controlPort)
        assertEquals(car.telemetryPort, session.telemetryPort)
        assertEquals(car.videoPort, session.videoPort)
        assertEquals(car.token, session.token)
        assertEquals(30, session.expiresInS)
    }

    @Test
    fun `une voiture deja revendiquee remonte comme telle, pas comme une panne reseau`() {
        car.claimStatus = 409

        assertThrows(CarAlreadyClaimedException::class.java) {
            runBlocking { adapter.claim("car-01") }
        }
    }

    @Test
    fun `un Gateway injoignable remonte en GatewayUnreachableException`() {
        adapter.configure(car.host, closedPort())

        assertThrows(GatewayUnreachableException::class.java) {
            runBlocking { adapter.listCars() }
        }
    }

    /** Un port qu'on vient de libérer : personne n'écoute derrière. */
    private fun closedPort(): Int = ServerSocket(0).use { it.localPort }
}
