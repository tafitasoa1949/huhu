package com.smartcar.pilot.domain.port

import com.smartcar.pilot.domain.model.CarSession
import kotlinx.coroutines.flow.Flow

/**
 * Port sortant (driven) du flux vidéo FPV — Phase 2 (docs/mobile-protocol.md,
 * §Flux vidéo). Décision tranchée : relais MJPEG brut par le Raspberry Pi,
 * sans réencodage (le Pi 5 n'a pas d'encodeur H.264 matériel — voir
 * docs/architecture.md, §Décisions bloquantes). L'implémentation réelle
 * (HTTP multipart) vit dans `app`, ce port ne connaît que l'intention :
 * ouvrir le flux d'une session revendiquée, observer les frames JPEG
 * décodées, le refermer.
 *
 * Chaque élément de [observe] est un JPEG complet (une partie du multipart
 * `multipart/x-mixed-replace`), pas un `Bitmap` : ce module reste du
 * Kotlin/JVM pur, le décodage image appartient à l'adaptateur d'entrée UI
 * (`app`, seul module qui dépende du SDK Android).
 */
interface VideoStreamPort {
    suspend fun open(session: CarSession)

    /** Une émission par frame JPEG reçue, tant que la liaison tient. */
    fun observe(): Flow<ByteArray>

    suspend fun close()
}
