package com.smartcar.pilot.di

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
import kotlinx.coroutines.CoroutineScope

/**
 * Racine de composition (pas de framework de DI — l'app est trop petite pour
 * le justifier, même principe que le reste du dépôt). Câble les adaptateurs
 * concrets (Android/OkHttp/sockets) derrière les ports du domaine, une seule
 * fois pour toute la durée de vie du process : il n'y a qu'une session de
 * pilotage possible à la fois.
 */
object AppContainer {

    private val gateway = GatewayHttpAdapter()
    private val control = UdpCarControlAdapter()
    private val telemetry = TcpCarTelemetryAdapter()
    private val video = MjpegVideoStreamAdapter()

    private val discoverCars = DiscoverCarsUseCase(gateway)
    private val connectToCar = ConnectToCarUseCase(gateway, control, telemetry, video)
    private val drive = DriveUseCase(control)
    private val emergencyStop = EmergencyStopUseCase(control)
    private val setMode = SetModeUseCase(control)
    private val disconnect = DisconnectUseCase(control, telemetry, video)

    fun configureGateway(host: String, port: Int) = gateway.configure(host, port)

    fun newPilotSession(scope: CoroutineScope): CarPilotSession = CarPilotSession(
        discoverCars = discoverCars,
        connectToCar = connectToCar,
        drive = drive,
        emergencyStop = emergencyStop,
        setMode = setMode,
        disconnect = disconnect,
        telemetry = telemetry,
        video = video,
        scope = scope,
    )
}
