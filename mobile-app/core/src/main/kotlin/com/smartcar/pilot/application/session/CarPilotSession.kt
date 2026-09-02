package com.smartcar.pilot.application.session

import com.smartcar.pilot.application.control.SequenceCounter
import com.smartcar.pilot.application.usecase.ConnectToCarUseCase
import com.smartcar.pilot.application.usecase.DisconnectUseCase
import com.smartcar.pilot.application.usecase.DiscoverCarsUseCase
import com.smartcar.pilot.application.usecase.DriveUseCase
import com.smartcar.pilot.application.usecase.EmergencyStopUseCase
import com.smartcar.pilot.application.usecase.SetModeUseCase
import com.smartcar.pilot.application.watchdog.ConnectionWatchdog
import com.smartcar.pilot.domain.model.CarSummary
import com.smartcar.pilot.domain.model.ConnectionState
import com.smartcar.pilot.domain.model.DrivingMode
import com.smartcar.pilot.domain.model.TelemetryFrame
import com.smartcar.pilot.domain.port.CarTelemetryPort
import com.smartcar.pilot.domain.port.VideoStreamPort
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Point d'entrée unique côté UI (adaptateur d'entrée) : la vue ne connaît
 * que cette classe, jamais les ports ni leurs implémentations — c'est elle
 * qui orchestre les cas d'usage et expose l'état observable
 * (docs/mobile-protocol.md décrit le protocole ; ce fichier décrit
 * uniquement l'enchaînement des appels).
 *
 * `scope` est fourni par l'appelant (le `viewModelScope` d'Android, par
 * exemple) : cette classe reste du Kotlin/JVM pur, elle ne sait pas d'où
 * vient ce `CoroutineScope`.
 */
class CarPilotSession(
    private val discoverCars: DiscoverCarsUseCase,
    private val connectToCar: ConnectToCarUseCase,
    private val drive: DriveUseCase,
    private val emergencyStop: EmergencyStopUseCase,
    private val setMode: SetModeUseCase,
    private val disconnect: DisconnectUseCase,
    private val telemetry: CarTelemetryPort,
    private val video: VideoStreamPort,
    private val scope: CoroutineScope,
    private val watchdog: ConnectionWatchdog = ConnectionWatchdog(),
) {
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Idle)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()

    private val _availableCars = MutableStateFlow<List<CarSummary>>(emptyList())
    val availableCars: StateFlow<List<CarSummary>> = _availableCars.asStateFlow()

    private val _latestTelemetry = MutableStateFlow<TelemetryFrame?>(null)
    val latestTelemetry: StateFlow<TelemetryFrame?> = _latestTelemetry.asStateFlow()

    // Relais MJPEG brut du Raspberry Pi (docs/mobile-protocol.md, §Flux
    // vidéo) : seule la dernière frame décodée compte pour l'affichage, pas
    // la peine de mettre en file les images sautées entre deux collectes UI.
    private val _latestVideoFrame = MutableStateFlow<ByteArray?>(null)
    val latestVideoFrame: StateFlow<ByteArray?> = _latestVideoFrame.asStateFlow()

    // MANUAL par défaut : c'est le seul mode que la voiture applique tant
    // qu'aucune couche autonome ne tourne côté Raspberry Pi (docs/tasks.md).
    // Mise à jour optimiste au clic, puis recalée sur ce que la télémétrie
    // rapporte réellement — même principe que speedPct/steeringPct.
    private val _currentMode = MutableStateFlow(DrivingMode.MANUAL)
    val currentMode: StateFlow<DrivingMode> = _currentMode.asStateFlow()

    private val sequence = SequenceCounter()
    private var telemetryJob: Job? = null
    private var videoJob: Job? = null
    private var watchdogJob: Job? = null
    private var lastFrameAtMs: Long = 0L

    fun refreshAvailableCars() {
        scope.launch {
            _connectionState.value = ConnectionState.Discovering
            runCatching { discoverCars() }
                .onSuccess {
                    _availableCars.value = it
                    _connectionState.value = ConnectionState.Idle
                }
                .onFailure { _connectionState.value = ConnectionState.Failed(it.message ?: "Gateway injoignable") }
        }
    }

    fun connect(carId: String) {
        scope.launch {
            _connectionState.value = ConnectionState.Associating
            runCatching { connectToCar(carId) }
                .onSuccess {
                    startTelemetryLoop()
                    startVideoLoop()
                    _connectionState.value = ConnectionState.Connected
                }
                .onFailure { _connectionState.value = ConnectionState.Failed(it.message ?: "association refusée") }
        }
    }

    /** À appeler en continu à 20 Hz pendant que l'écran de conduite est affiché (PDF §Phase 3). */
    fun onJoystick(throttleAxis: Float, steeringAxis: Float) {
        scope.launch { runCatching { drive(sequence, throttleAxis, steeringAxis) } }
    }

    fun onEmergencyStop() {
        scope.launch { runCatching { emergencyStop(sequence) } }
    }

    fun onSetMode(mode: DrivingMode) {
        _currentMode.value = mode
        scope.launch { runCatching { setMode(sequence, mode) } }
    }

    fun endSession() {
        telemetryJob?.cancel()
        videoJob?.cancel()
        watchdogJob?.cancel()
        scope.launch { runCatching { disconnect() } }
        _connectionState.value = ConnectionState.Disconnected
        _latestVideoFrame.value = null
    }

    private fun startTelemetryLoop() {
        lastFrameAtMs = System.currentTimeMillis()

        telemetryJob?.cancel()
        telemetryJob = scope.launch {
            telemetry.observe().collect { frame ->
                lastFrameAtMs = System.currentTimeMillis()
                _latestTelemetry.value = frame
                // La voiture a le dernier mot sur le mode réellement actif
                // (même principe que speedPct/steeringPct) — mais seulement
                // si elle le rapporte : un ancien firmware qui ne connaît
                // pas ce champ ne doit pas faire régresser le bouton vers
                // MANUAL à chaque trame.
                frame.mode?.let { _currentMode.value = it }
                if (_connectionState.value == ConnectionState.LinkLost) {
                    _connectionState.value = ConnectionState.Connected
                }
            }
        }

        watchdogJob?.cancel()
        watchdogJob = scope.launch {
            while (true) {
                delay(WATCHDOG_CHECK_PERIOD_MS)
                if (_connectionState.value == ConnectionState.Connected &&
                    watchdog.isLinkLost(lastFrameAtMs, System.currentTimeMillis())
                ) {
                    _connectionState.value = ConnectionState.LinkLost
                }
            }
        }
    }

    private fun startVideoLoop() {
        videoJob?.cancel()
        videoJob = scope.launch {
            video.observe().collect { jpegFrame -> _latestVideoFrame.value = jpegFrame }
        }
    }

    private companion object {
        const val WATCHDOG_CHECK_PERIOD_MS = 500L
    }
}
