package com.smartcar.pilot.adapter.outbound.p2p

import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.model.ControlMessage
import com.smartcar.pilot.domain.port.CarControlPort
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Canal de contrôle P2P — UDP, app -> voiture (docs/mobile-protocol.md,
 * Phase 2). Fire-and-forget par construction : aucune confirmation
 * attendue, une commande périmée doit être remplacée par la suivante, pas
 * retransmise.
 */
class UdpCarControlAdapter : CarControlPort {

    private var socket: DatagramSocket? = null
    private var address: InetAddress? = null
    private var port: Int = 0
    private var token: String = ""

    override suspend fun open(session: CarSession) = withContext(Dispatchers.IO) {
        socket = DatagramSocket()
        address = InetAddress.getByName(session.ip)
        port = session.controlPort
        token = session.token
    }

    override suspend fun send(message: ControlMessage) = withContext(Dispatchers.IO) {
        val currentSocket = socket ?: return@withContext
        val currentAddress = address ?: return@withContext
        val bytes = message.toWireJson(token).toByteArray(Charsets.UTF_8)
        currentSocket.send(DatagramPacket(bytes, bytes.size, currentAddress, port))
    }

    override suspend fun close() = withContext(Dispatchers.IO) {
        socket?.close()
        socket = null
        address = null
    }
}
