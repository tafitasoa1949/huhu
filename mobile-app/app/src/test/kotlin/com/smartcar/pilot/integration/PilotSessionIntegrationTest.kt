package com.smartcar.pilot.integration

import com.smartcar.pilot.adapter.outbound.gateway.GatewayHttpAdapter
import com.smartcar.pilot.adapter.outbound.p2p.TcpCarTelemetryAdapter
import com.smartcar.pilot.adapter.outbound.p2p.UdpCarControlAdapter
import com.smartcar.pilot.adapter.outbound.video.MjpegVideoStreamAdapter
import com.smartcar.pilot.application.session.CarPilotSession
import com.smartcar.pilot.application.usecase.ConnectToCarUseCase
import com.smartcar.pilot.application.usecase.DisconnectUseCase
import com.smartcar.pilot.application.usecase.DiscoverCarsUseCase
import com.smartcar.pilot.application.usecase.DriveUseCase
import com.smartcar.pilot.application.usecase.EmergencyStopUseCase
import com.smartcar.pilot.application.usecase.SetModeUseCase
import com.smartcar.pilot.application.watchdog.ConnectionWatchdog
import com.smartcar.pilot.domain.model.ConnectionState
import com.smartcar.pilot.domain.model.DrivingMode
import com.smartcar.pilot.testsupport.FakeCar
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

/**
 * Test d'intégration : la session de pilotage complète, du `GET /api/cars`
 * jusqu'au joystick, à travers les vrais adaptateurs réseau et une fausse
 * voiture sur vrais sockets ([FakeCar]). Rien n'est simulé côté app — ni le
 * transport, ni le format des paquets : ce qui est simulé, ce sont les
 * conditions rencontrées en test manuel (voiture déjà prise, télémétrie qui
 * se tait, vidéo qui arrive).
 *
 * C'est le filet qui manquait : chacun des bugs vus en démonstration
 * (fond vidéo noir, commandes jamais appliquées) traversait plusieurs
 * couches à la fois et passait donc entre les mailles des tests unitaires
 * de `core`, qui ne parlent qu'à des doublures.
 */
class PilotSessionIntegrationTest {

    private lateinit var car: FakeCar
    private lateinit var control: UdpCarControlAdapter
    private lateinit var telemetry: TcpCarTelemetryAdapter
    private lateinit var video: MjpegVideoStreamAdapter
    private lateinit var session: CarPilotSession
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    @Before
    fun setUp() {
        car = FakeCar()
        val gateway = GatewayHttpAdapter().apply { configure(car.host, car.gatewayPort) }
        control = UdpCarControlAdapter()
        telemetry = TcpCarTelemetryAdapter()
        video = MjpegVideoStreamAdapter()
        session = CarPilotSession(
            discoverCars = DiscoverCarsUseCase(gateway),
            connectToCar = ConnectToCarUseCase(gateway, control, telemetry, video),
            drive = DriveUseCase(control),
            emergencyStop = EmergencyStopUseCase(control),
            setMode = SetModeUseCase(control),
            disconnect = DisconnectUseCase(control, telemetry, video),
            telemetry = telemetry,
            video = video,
            scope = scope,
            // Raccourci pour ne pas faire durer le test 2 s : la règle
            // métier (2000 ms) est déjà couverte par ConnectionWatchdogTest.
            watchdog = ConnectionWatchdog(timeoutMs = 300L),
        )
    }

    @After
    fun tearDown() {
        scope.cancel()
        car.close()
    }

    @Test
    fun `de la decouverte au joystick, la chaine complete passe par le reseau`() {
        session.refreshAvailableCars()
        awaitUntil("la voiture n'est jamais apparue dans la liste") {
            session.availableCars.value.isNotEmpty()
        }
        assertEquals("car-01", session.availableCars.value.single().carId)

        session.connect("car-01")
        awaitUntil("la session n'est jamais passée en Connected") {
            session.connectionState.value == ConnectionState.Connected
        }
        // Un seul claim par connexion : chaque claim de plus fait émettre un
        // nouveau jeton à la voiture, qui rejette alors toutes les commandes
        // portant le précédent (condition observée en test manuel).
        assertEquals(1, car.claimCount.get())

        // Phase 3 : le joystick à fond en avant, braqué à mi-course à gauche.
        session.onJoystick(throttleAxis = 1f, steeringAxis = -0.5f)
        val raw = car.receiveControlPacket()
        assertNotNull("aucune commande n'est arrivée sur le canal UDP de la voiture", raw)
        val packet = Json.parseToJsonElement(raw!!).jsonObject
        assertEquals("drive", packet.getValue("type").jsonPrimitive.content)
        assertEquals(car.token, packet.getValue("token").jsonPrimitive.content)
        assertEquals(100, packet.getValue("speed_pct").jsonPrimitive.int)
        assertEquals(-50, packet.getValue("steering_pct").jsonPrimitive.int)

        // La voiture répond : sa télémétrie fait autorité sur ce qui est appliqué.
        car.awaitTelemetryClient()
        car.pushTelemetry(
            """{"type":"telemetry","seq":1,"ts_ms":1,"speed_pct":40,"steering_pct":-15,""" +
                """"battery_pct":76,"rssi_dbm":-58,"mode":"AUTO"}""",
        )
        awaitUntil("aucune télémétrie n'est remontée jusqu'à l'état de session") {
            session.latestTelemetry.value != null
        }
        assertEquals(40, session.latestTelemetry.value!!.speedPct)
        assertEquals(DrivingMode.AUTO, session.currentMode.value)

        // Et la vidéo : régression du fond noir permanent.
        car.pushVideoFrame(ByteArray(300) { 7.toByte() })
        awaitUntil("aucune frame vidéo n'est parvenue jusqu'à l'écran") {
            session.latestVideoFrame.value != null
        }
        assertEquals(7, session.latestVideoFrame.value!![0].toInt())
    }

    @Test
    fun `le silence de la telemetrie bascule en liaison perdue, puis se retablit`() {
        session.connect("car-01")
        awaitUntil("la session n'est jamais passée en Connected") {
            session.connectionState.value == ConnectionState.Connected
        }
        car.awaitTelemetryClient()

        // Plus rien ne remonte : la voiture a déjà coupé les moteurs de son
        // côté (watchdog embarqué), l'app doit le dire au pilote.
        awaitUntil("la perte de liaison n'a pas été détectée") {
            session.connectionState.value == ConnectionState.LinkLost
        }

        car.pushTelemetry(
            """{"type":"telemetry","seq":2,"ts_ms":2,"speed_pct":0,"steering_pct":0,""" +
                """"battery_pct":null,"rssi_dbm":null,"mode":"MANUAL"}""",
        )
        awaitUntil("la liaison ne s'est pas rétablie à la trame suivante") {
            session.connectionState.value == ConnectionState.Connected
        }
    }

    @Test
    fun `une voiture deja revendiquee laisse la session en echec, pas en pilotage`() {
        car.claimStatus = 409

        session.connect("car-01")
        awaitUntil("la session n'a pas signalé l'échec d'association") {
            session.connectionState.value is ConnectionState.Failed
        }
        val state = session.connectionState.value as ConnectionState.Failed
        assertTrue(
            "la raison affichée doit parler de la voiture, pas d'un code HTTP brut : ${state.reason}",
            state.reason.contains("revendiquée"),
        )
    }

    @Test
    fun `l arret d urgence part sur le canal de controle sans attendre le tick suivant`() {
        session.connect("car-01")
        awaitUntil("la session n'est jamais passée en Connected") {
            session.connectionState.value == ConnectionState.Connected
        }

        session.onEmergencyStop()

        val raw = car.receiveControlPacket()
        assertNotNull("l'arrêt d'urgence n'est jamais arrivé à la voiture", raw)
        assertEquals(
            "emergency",
            Json.parseToJsonElement(raw!!).jsonObject.getValue("type").jsonPrimitive.content,
        )
    }

    private fun awaitUntil(message: String, timeoutMs: Long = 5000, condition: () -> Boolean) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (condition()) return
            Thread.sleep(20)
        }
        fail(message)
    }
}
