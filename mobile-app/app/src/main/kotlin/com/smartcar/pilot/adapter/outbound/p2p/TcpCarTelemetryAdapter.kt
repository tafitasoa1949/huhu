package com.smartcar.pilot.adapter.outbound.p2p

import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.model.TelemetryFrame
import com.smartcar.pilot.domain.port.CarTelemetryPort
import java.io.BufferedReader
import java.io.IOException
import java.net.Socket
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext

/**
 * Canal de télémétrie P2P — TCP, voiture -> app (docs/mobile-protocol.md,
 * Phase 2). TCP plutôt qu'UDP ici : contrairement au contrôle, une trame de
 * télémétrie perdue n'a pas vocation à être remplacée par la suivante à
 * haute fréquence, l'ordre et la fiabilité comptent plus que la fraîcheur
 * absolue.
 */
class TcpCarTelemetryAdapter : CarTelemetryPort {

    private var socket: Socket? = null
    private var reader: BufferedReader? = null

    override suspend fun open(session: CarSession) = withContext(Dispatchers.IO) {
        val newSocket = Socket(session.ip, session.telemetryPort)
        socket = newSocket
        reader = newSocket.getInputStream().bufferedReader()
    }

    override fun observe(): Flow<TelemetryFrame> = flow {
        val currentReader = reader ?: return@flow
        while (true) {
            val line = try {
                currentReader.readLine()
            } catch (e: IOException) {
                null
            } ?: break
            parseTelemetryLine(line)?.let { emit(it) }
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun close() = withContext(Dispatchers.IO) {
        runCatching { reader?.close() }
        runCatching { socket?.close() }
        reader = null
        socket = null
    }
}
