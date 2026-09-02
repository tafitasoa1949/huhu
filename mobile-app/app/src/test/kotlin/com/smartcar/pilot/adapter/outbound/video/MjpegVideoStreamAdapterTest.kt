package com.smartcar.pilot.adapter.outbound.video

import com.smartcar.pilot.testsupport.FakeCar
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Before
import org.junit.Test

/**
 * Découpage du flux MJPEG relayé par le Raspberry Pi (docs/mobile-protocol.md,
 * §Flux vidéo), contre un vrai serveur `multipart/x-mixed-replace`.
 *
 * Le premier test est une régression : la règle « ne pas afficher une frame
 * déjà périmée » s'appuyait sur `buffer.isNotEmpty() || available() > 0`,
 * toujours vrai à cause de la sur-lecture par blocs de 4 Ko — *toutes* les
 * images étaient sautées et l'écran de conduite restait noir en permanence.
 */
class MjpegVideoStreamAdapterTest {

    private lateinit var car: FakeCar
    private lateinit var adapter: MjpegVideoStreamAdapter
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    @Before
    fun setUp() = runBlocking {
        car = FakeCar()
        adapter = MjpegVideoStreamAdapter()
        adapter.open(car.session())
    }

    @After
    fun tearDown() = runBlocking {
        scope.cancel()
        adapter.close()
        car.close()
    }

    @Test
    fun `chaque frame est emise tant que le consommateur suit le rythme`() {
        val received = LinkedBlockingQueue<ByteArray>()
        scope.launch { adapter.observe().collect { received.put(it) } }

        // Une image à la fois, chacune attendue avant d'envoyer la suivante :
        // le lecteur n'a jamais de retard, donc aucune n'a de raison d'être
        // sautée.
        for (id in 1..3) {
            car.pushVideoFrame(frame(id))
            val got = received.poll(5, TimeUnit.SECONDS)
            assertNotNull("frame $id jamais émise par l'adaptateur", got)
            assertEquals(id, got!![0].toInt())
        }
    }

    @Test
    fun `seule la frame la plus fraiche est emise quand le consommateur decroche`() {
        val received = LinkedBlockingQueue<ByteArray>()
        val emitted = AtomicInteger(0)
        scope.launch {
            adapter.observe().collect {
                received.put(it)
                // Consommateur lent (décodage bitmap, écran occupé...) : le
                // lecteur ne lit rien pendant ce temps, les images suivantes
                // s'accumulent dans le tampon TCP.
                if (emitted.incrementAndGet() == 1) delay(500)
            }
        }

        car.pushVideoFrame(frame(1))
        val first = received.poll(5, TimeUnit.SECONDS)
        assertNotNull("première frame jamais émise", first)
        assertEquals(1, first!![0].toInt())

        for (id in 2..5) {
            car.pushVideoFrame(frame(id))
        }

        val next = received.poll(5, TimeUnit.SECONDS)
        assertNotNull("aucune frame émise après le retard", next)
        assertEquals(
            "les frames 2 à 4 sont périmées à l'arrivée : seule la dernière doit être affichée",
            5,
            next!![0].toInt(),
        )
    }

    @Test
    fun `le jeton de session est presente en parametre de requete`() {
        scope.launch { adapter.observe().collect { } }
        car.pushVideoFrame(frame(1))

        assertEquals("token=${car.token}", car.awaitVideoQuery())
    }

    /** Charge utile reconnaissable : tous les octets valent l'identifiant de la frame. */
    private fun frame(id: Int): ByteArray = ByteArray(200) { id.toByte() }
}
