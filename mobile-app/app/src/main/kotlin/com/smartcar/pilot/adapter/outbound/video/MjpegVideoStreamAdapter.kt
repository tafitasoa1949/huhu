package com.smartcar.pilot.adapter.outbound.video

import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.port.VideoStreamPort
import java.io.EOFException
import java.io.IOException
import java.io.InputStream
import java.util.regex.Pattern
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response

/**
 * Canal vidéo P2P — relais MJPEG brut du Raspberry Pi (docs/mobile-protocol.md,
 * §Flux vidéo ; décision : pas de réencodage, le Pi 5 n'a pas d'encodeur H.264
 * matériel). Le Pi reproxifie tel quel le flux `multipart/x-mixed-replace` de
 * l'ESP32-CAM (même format de trame que
 * `vehicle/raspberry-pi/src/smart_car/vision/mjpeg_source.py` côté Python) :
 * `--frame`, en-têtes `Content-Type`/`Content-Length`, `\r\n\r\n`, payload
 * JPEG, on recommence.
 *
 * Pas d'ExoPlayer ici : son support MJPEG multipart est limité, et un simple
 * découpage de flux HTTP suffit pour un `Flow<ByteArray>` de JPEG que la
 * couche UI décode elle-même image par image.
 */
class MjpegVideoStreamAdapter(
    private val client: OkHttpClient = OkHttpClient(),
) : VideoStreamPort {

    @Volatile
    private var session: CarSession? = null

    @Volatile
    private var response: Response? = null

    override suspend fun open(session: CarSession) {
        this.session = session
    }

    override fun observe(): Flow<ByteArray> = flow {
        val currentSession = session ?: return@flow
        // Jeton en requête (docs/mobile-protocol.md) : contrairement au
        // contrôle/télémétrie, ce canal est un simple GET HTTP, il n'a pas
        // d'autre moyen de prouver la session au Raspberry Pi.
        val url = "http://${currentSession.ip}:${currentSession.videoPort}/stream?token=${currentSession.token}"
        val request = Request.Builder().url(url).build()

        val currentResponse = try {
            client.newCall(request).execute()
        } catch (e: IOException) {
            return@flow
        }
        response = currentResponse

        val body = currentResponse.body ?: return@flow
        val reader = MjpegMultipartReader(body.byteStream())
        while (true) {
            val frame = try {
                reader.nextFrame()
            } catch (e: IOException) {
                break
            } catch (e: EOFException) {
                break
            }
            // Canal HTTP/TCP, pas UDP : rien ne fait sauter les trames en
            // retard côté transport. Si une frame suivante est déjà arrivée
            // pendant qu'on lisait celle-ci, celle qu'on vient de décoder
            // est déjà périmée — on ne l'affiche pas et on enchaîne
            // directement sur la suivante, plutôt que de laisser le retard
            // s'accumuler et rejouer tout le tampon en rafale (même
            // principe que les paquets de contrôle obsolètes ignorés,
            // docs/mobile-protocol.md).
            if (reader.hasBufferedData()) continue
            emit(frame)
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun close() = withContext(Dispatchers.IO) {
        runCatching { response?.close() }
        response = null
        session = null
    }
}

/**
 * Découpe un flux `multipart/x-mixed-replace;boundary=frame` en JPEG
 * complets. Miroir Kotlin de `_ChunkedReader`/`MjpegFrameSource`
 * (`vehicle/raspberry-pi/src/smart_car/vision/mjpeg_source.py`) — même
 * boundary (`--frame`), même en-tête `Content-Length` obligatoire.
 */
private class MjpegMultipartReader(private val input: InputStream) {

    private var buffer = ByteArray(0)

    fun nextFrame(): ByteArray {
        readUntil(BOUNDARY)
        val header = readUntil(HEADER_END)
        val matcher = CONTENT_LENGTH.matcher(String(header, Charsets.US_ASCII))
        if (!matcher.find()) throw IOException("en-tête de partie MJPEG sans Content-Length")
        val length = matcher.group(1)!!.toInt()
        return readExact(length)
    }

    /**
     * Signale qu'une frame plus récente attend déjà d'être lue — soit dans
     * le reliquat qu'on a déjà tiré du flux (sur-lecture par blocs de
     * [CHUNK_SIZE]), soit directement disponible côté OS sans bloquer.
     * `InputStream.available()` n'est qu'une estimation, mais suffisante
     * ici : elle sert seulement à décider si la frame qu'on vient de finir
     * de lire vaut la peine d'être affichée, pas à dimensionner une lecture.
     */
    fun hasBufferedData(): Boolean = buffer.isNotEmpty() || input.available() > 0

    private fun fill(): Boolean {
        val chunk = ByteArray(CHUNK_SIZE)
        val read = input.read(chunk)
        if (read <= 0) return false
        buffer += chunk.copyOf(read)
        return true
    }

    private fun readUntil(marker: ByteArray): ByteArray {
        while (true) {
            val index = indexOf(buffer, marker)
            if (index != -1) {
                val end = index + marker.size
                val data = buffer.copyOfRange(0, end)
                buffer = buffer.copyOfRange(end, buffer.size)
                return data
            }
            if (!fill()) throw EOFException("flux MJPEG terminé avant de trouver la frontière")
        }
    }

    private fun readExact(count: Int): ByteArray {
        while (buffer.size < count) {
            if (!fill()) throw EOFException("flux MJPEG terminé avant la fin de l'image annoncée")
        }
        val data = buffer.copyOfRange(0, count)
        buffer = buffer.copyOfRange(count, buffer.size)
        return data
    }

    private fun indexOf(haystack: ByteArray, needle: ByteArray): Int {
        if (needle.isEmpty() || haystack.size < needle.size) return -1
        outer@ for (i in 0..haystack.size - needle.size) {
            for (j in needle.indices) {
                if (haystack[i + j] != needle[j]) continue@outer
            }
            return i
        }
        return -1
    }

    private companion object {
        val BOUNDARY = "--frame".toByteArray(Charsets.US_ASCII)
        val HEADER_END = "\r\n\r\n".toByteArray(Charsets.US_ASCII)
        val CONTENT_LENGTH: Pattern = Pattern.compile("Content-Length:\\s*(\\d+)", Pattern.CASE_INSENSITIVE)
        const val CHUNK_SIZE = 4096
    }
}
