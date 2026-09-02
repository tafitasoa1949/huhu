package com.smartcar.pilot.domain.port

import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.model.ControlMessage

/**
 * Port sortant (driven) du canal de contrôle P2P — Phase 2
 * (docs/mobile-protocol.md). L'implémentation réelle (UDP) vit dans `app`,
 * ce port ne connaît que l'intention : ouvrir un canal vers une session
 * revendiquée, y envoyer des messages, le refermer.
 */
interface CarControlPort {
    suspend fun open(session: CarSession)
    suspend fun send(message: ControlMessage)
    suspend fun close()
}
