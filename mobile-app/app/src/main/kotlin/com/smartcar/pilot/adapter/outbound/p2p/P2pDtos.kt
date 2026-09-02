package com.smartcar.pilot.adapter.outbound.p2p

import com.smartcar.pilot.domain.model.ControlMessage
import com.smartcar.pilot.domain.model.DrivingMode
import com.smartcar.pilot.domain.model.TelemetryFrame
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json

/** Corps JSON des paquets P2P (docs/mobile-protocol.md, Phase 2). Noms de champs imposés côté fil. */
@Serializable
private data class DriveMessageDto(
    val type: String = "drive",
    val token: String,
    val seq: Int,
    @SerialName("ts_ms") val tsMs: Long,
    @SerialName("speed_pct") val speedPct: Int,
    @SerialName("steering_pct") val steeringPct: Int,
)

@Serializable
private data class EmergencyMessageDto(
    val type: String = "emergency",
    val token: String,
    val seq: Int,
    @SerialName("ts_ms") val tsMs: Long,
)

@Serializable
private data class SetModeMessageDto(
    val type: String = "mode",
    val token: String,
    val seq: Int,
    @SerialName("ts_ms") val tsMs: Long,
    val mode: String,
)

@Serializable
private data class TelemetryFrameDto(
    val type: String = "telemetry",
    val seq: Int,
    @SerialName("ts_ms") val tsMs: Long,
    @SerialName("speed_pct") val speedPct: Int? = null,
    @SerialName("steering_pct") val steeringPct: Int? = null,
    @SerialName("battery_pct") val batteryPct: Int? = null,
    @SerialName("rssi_dbm") val rssiDbm: Int? = null,
    val mode: String? = null,
)

private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

/** Sérialise un [ControlMessage] pour un paquet UDP, jeton inclus. */
fun ControlMessage.toWireJson(token: String): String = when (this) {
    is ControlMessage.Drive -> json.encodeToString(
        DriveMessageDto.serializer(),
        DriveMessageDto(token = token, seq = sequence, tsMs = tsMs, speedPct = speedPct, steeringPct = steeringPct),
    )
    is ControlMessage.Emergency -> json.encodeToString(
        EmergencyMessageDto.serializer(),
        EmergencyMessageDto(token = token, seq = sequence, tsMs = tsMs),
    )
    is ControlMessage.SetMode -> json.encodeToString(
        SetModeMessageDto.serializer(),
        SetModeMessageDto(token = token, seq = sequence, tsMs = tsMs, mode = mode.name),
    )
}

/**
 * Décode une ligne du flux TCP de télémétrie. Renvoie `null` pour une ligne
 * mal formée plutôt que de lever une exception — un flux réseau ligne par
 * ligne finit toujours par recevoir un fragment coupé (même principe que
 * `parseServerMessage` dans l'ancienne implémentation WebSocket).
 */
fun parseTelemetryLine(rawJson: String): TelemetryFrame? = try {
    val dto = json.decodeFromString(TelemetryFrameDto.serializer(), rawJson)
    TelemetryFrame(
        sequence = dto.seq,
        tsMs = dto.tsMs,
        speedPct = dto.speedPct,
        steeringPct = dto.steeringPct,
        batteryPct = dto.batteryPct,
        rssiDbm = dto.rssiDbm,
        // Valeur inconnue/mal formée = null, jamais une exception : une
        // voiture qui n'a pas encore ce champ (protocole plus ancien) ne
        // doit pas faire échouer le parsing de toute la trame.
        mode = dto.mode?.let { raw -> runCatching { DrivingMode.valueOf(raw) }.getOrNull() },
    )
} catch (e: SerializationException) {
    null
}
