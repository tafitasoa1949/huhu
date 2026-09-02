package com.smartcar.pilot.adapter.inbound.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.smartcar.pilot.di.AppContainer
import com.smartcar.pilot.domain.model.DrivingMode

/**
 * Relie les écrans à [com.smartcar.pilot.application.session.CarPilotSession]
 * — le seul point de contact avec le domaine/l'application. Ne connaît ni
 * les ports ni leurs adaptateurs (docs/mobile-protocol.md).
 */
class DrivingViewModel : ViewModel() {

    private val session by lazy { AppContainer.newPilotSession(viewModelScope) }

    val connectionState get() = session.connectionState
    val availableCars get() = session.availableCars
    val latestTelemetry get() = session.latestTelemetry
    val latestVideoFrame get() = session.latestVideoFrame
    val currentMode get() = session.currentMode

    /** Phase 1 (PDF §Phase 1) : configure l'adresse du Gateway puis liste les voitures. */
    fun searchCars(gatewayHost: String, gatewayPort: Int) {
        AppContainer.configureGateway(gatewayHost, gatewayPort)
        session.refreshAvailableCars()
    }

    /** Bascule Phase 1 -> Phase 2 : revendique la voiture choisie, ouvre les canaux P2P. */
    fun selectCar(carId: String) = session.connect(carId)

    /** À appeler en continu à 20 Hz depuis l'écran de conduite (PDF §Phase 3). */
    fun onJoystick(throttleAxis: Float, steeringAxis: Float) = session.onJoystick(throttleAxis, steeringAxis)

    fun emergencyStop() = session.onEmergencyStop()

    fun setMode(mode: DrivingMode) = session.onSetMode(mode)

    override fun onCleared() = session.endSession()
}
