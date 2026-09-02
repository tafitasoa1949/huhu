package com.smartcar.pilot.testsupport

import com.smartcar.pilot.domain.model.CarSession
import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import java.io.IOException
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.nio.charset.StandardCharsets
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/**
 * Fausse voiture complète, sur vrais sockets en boucle locale : Gateway REST
 * (Phase 1), contrôle UDP, télémétrie TCP et relais MJPEG (Phase 2) —
 * exactement les quatre canaux de `docs/mobile-protocol.md`.
 *
 * Volontairement pas de mock des adaptateurs : les seuls bugs qu'on a
 * réellement rencontrés (aucune frame vidéo affichée, commandes rejetées)
 * vivaient dans le code de transport lui-même, que des doublures auraient
 * justement court-circuité. Tout ce qui est simulé ici, ce sont les
 * *conditions* : cadence des trames, consommateur en retard, voiture déjà
 * revendiquée, silence de la télémétrie.
 *
 * Équivalent Kotlin de `tools/fake_car_harness.py`, réduit à ce qu'un test
 * doit pouvoir piloter image par image.
 */
class FakeCar(
    private val carId: String = "car-01",
    private val carName: String = "Voiture de test",
    val token: String = "tok-test",
) : AutoCloseable {

    private val loopback: InetAddress = InetAddress.getByName("127.0.0.1")
    private val executor = Executors.newCachedThreadPool()

    private val controlSocket = DatagramSocket(0, loopback)
    private val telemetryServer = ServerSocket(0, 4, loopback)
    private val gatewayServer: HttpServer = HttpServer.create(InetSocketAddress(loopback, 0), 0)
    private val videoServer: HttpServer = HttpServer.create(InetSocketAddress(loopback, 0), 0)

    private val telemetryClients = CopyOnWriteArrayList<Socket>()
    private val videoFrames = LinkedBlockingQueue<ByteArray>()
    private val videoQuery = AtomicReference<String?>(null)

    /** Nombre de `POST /api/cars/{id}/claim` reçus — un claim de trop rebat le jeton de session. */
    val claimCount = AtomicInteger(0)

    /** Code que le Gateway simulé renvoie au prochain claim (409 = déjà revendiquée). */
    @Volatile
    var claimStatus: Int = 200

    val host: String = "127.0.0.1"
    val gatewayPort: Int get() = gatewayServer.address.port
    val controlPort: Int get() = controlSocket.localPort
    val telemetryPort: Int get() = telemetryServer.localPort
    val videoPort: Int get() = videoServer.address.port

    init {
        gatewayServer.executor = executor
        videoServer.executor = executor

        gatewayServer.createContext("/api/cars") { exchange ->
            respondJson(exchange, 200, """[{"car_id":"$carId","name":"$carName","online":true}]""")
        }
        // Contexte plus spécifique que "/api/cars" : `HttpServer` retient le
        // préfixe le plus long, c'est donc bien celui-ci qui sert le claim.
        gatewayServer.createContext("/api/cars/$carId/claim") { exchange ->
            claimCount.incrementAndGet()
            val status = claimStatus
            if (status == 200) {
                respondJson(exchange, 200, claimBody())
            } else {
                respondJson(exchange, status, """{"error":"claim refusé"}""")
            }
        }
        videoServer.createContext("/stream") { exchange -> streamVideo(exchange) }

        gatewayServer.start()
        videoServer.start()
        executor.execute { acceptTelemetryClients() }
    }

    /** La session que le Gateway renverrait pour cette voiture, sans passer par HTTP. */
    fun session(): CarSession = CarSession(
        carId = carId,
        ip = host,
        controlPort = controlPort,
        telemetryPort = telemetryPort,
        videoPort = videoPort,
        token = token,
        expiresInS = 30,
        claimedAtMs = System.currentTimeMillis(),
    )

    /** Lit un paquet du canal de contrôle UDP ; `null` si rien n'arrive à temps. */
    fun receiveControlPacket(timeoutMs: Int = 2000): String? {
        val buffer = ByteArray(4096)
        val packet = DatagramPacket(buffer, buffer.size)
        controlSocket.soTimeout = timeoutMs
        return try {
            controlSocket.receive(packet)
            String(packet.data, 0, packet.length, StandardCharsets.UTF_8)
        } catch (e: SocketTimeoutException) {
            null
        }
    }

    /** Pousse une ligne de télémétrie vers tous les clients TCP connectés. */
    fun pushTelemetry(line: String) {
        val bytes = (line + "\n").toByteArray(StandardCharsets.UTF_8)
        for (client in telemetryClients) {
            runCatching {
                client.getOutputStream().write(bytes)
                client.getOutputStream().flush()
            }
        }
    }

    /** Met une image de plus dans le flux MJPEG ; elle part dès que le relais la voit. */
    fun pushVideoFrame(jpeg: ByteArray) {
        videoFrames.put(jpeg)
    }

    /** Attend qu'un client de télémétrie soit accepté (l'app vient d'ouvrir la Phase 2). */
    fun awaitTelemetryClient(timeoutMs: Long = 5000) {
        awaitUntil(timeoutMs) { telemetryClients.isNotEmpty() }
    }

    /** Chaîne de requête du `GET /stream` reçu, une fois l'app connectée à la vidéo. */
    fun awaitVideoQuery(timeoutMs: Long = 5000): String? {
        awaitUntil(timeoutMs) { videoQuery.get() != null }
        return videoQuery.get()
    }

    override fun close() {
        runCatching { gatewayServer.stop(0) }
        runCatching { videoServer.stop(0) }
        runCatching { controlSocket.close() }
        telemetryClients.forEach { runCatching { it.close() } }
        runCatching { telemetryServer.close() }
        executor.shutdownNow()
    }

    private fun claimBody(): String =
        """{"car_id":"$carId","ip":"$host","control_port":$controlPort,""" +
            """"telemetry_port":$telemetryPort,"video_port":$videoPort,""" +
            """"token":"$token","expires_in_s":30}"""

    private fun respondJson(exchange: HttpExchange, status: Int, body: String) {
        val bytes = body.toByteArray(StandardCharsets.UTF_8)
        exchange.responseHeaders.add("Content-Type", "application/json")
        exchange.sendResponseHeaders(status, bytes.size.toLong())
        exchange.responseBody.use { it.write(bytes) }
    }

    /**
     * Même format binaire que le relais du Raspberry Pi
     * (`network/video_relay.py`) : `--frame`, `Content-Length`, `\r\n\r\n`,
     * payload, on recommence. Le flux reste ouvert tant que le test pousse
     * des images.
     */
    private fun streamVideo(exchange: HttpExchange) {
        videoQuery.set(exchange.requestURI.query ?: "")
        exchange.responseHeaders.add("Content-Type", "multipart/x-mixed-replace;boundary=frame")
        exchange.sendResponseHeaders(200, 0)
        try {
            val out = exchange.responseBody
            while (true) {
                val frame = videoFrames.poll(5, TimeUnit.SECONDS) ?: break
                out.write("\r\n--frame\r\n".toByteArray(StandardCharsets.US_ASCII))
                out.write(
                    "Content-Type: image/jpeg\r\nContent-Length: ${frame.size}\r\n\r\n"
                        .toByteArray(StandardCharsets.US_ASCII),
                )
                out.write(frame)
                out.flush()
            }
        } catch (e: IOException) {
            // Client parti : fin normale, comme le relais réel.
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
        } finally {
            exchange.close()
        }
    }

    private fun acceptTelemetryClients() {
        while (!telemetryServer.isClosed) {
            try {
                telemetryClients.add(telemetryServer.accept())
            } catch (e: IOException) {
                return
            }
        }
    }

    private fun awaitUntil(timeoutMs: Long, condition: () -> Boolean) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (condition()) return
            Thread.sleep(10)
        }
    }
}
