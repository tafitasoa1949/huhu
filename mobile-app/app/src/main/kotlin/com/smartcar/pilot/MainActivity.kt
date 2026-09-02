package com.smartcar.pilot

import android.app.Activity
import android.content.pm.ActivityInfo
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import com.smartcar.pilot.adapter.inbound.ui.ConnectionScreen
import com.smartcar.pilot.adapter.inbound.ui.DrivingScreen
import com.smartcar.pilot.adapter.inbound.ui.DrivingViewModel
import com.smartcar.pilot.adapter.inbound.ui.SmartCarTheme
import com.smartcar.pilot.domain.model.ConnectionState

/**
 * Point d'entrée unique. Pas de bibliothèque de navigation pour deux écrans
 * : l'état de connexion suffit à choisir lequel afficher (écrans 4 à 6 du
 * TODO restent à faire — Navigation Compose sera introduit quand il y aura
 * effectivement plusieurs destinations à enchaîner).
 */
class MainActivity : ComponentActivity() {

    private val viewModel: DrivingViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val connectionState by viewModel.connectionState.collectAsState()
            val isDriving = connectionState == ConnectionState.Connected || connectionState == ConnectionState.LinkLost

            // Écran de conduite : toujours sombre, quel que soit le thème système
            // (la vidéo plein cadre a besoin de panneaux HUD sombres pour rester
            // lisible — voir SmartCarTheme.kt). Écran de connexion : suit le thème
            // clair/sombre de l'appareil (paramètre par défaut de SmartCarTheme).
            SmartCarTheme(darkTheme = if (isDriving) true else isSystemInDarkTheme()) {
                Surface(modifier = Modifier.fillMaxSize()) {
                    when (connectionState) {
                        ConnectionState.Connected, ConnectionState.LinkLost -> {
                            LockOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE)
                            val telemetry by viewModel.latestTelemetry.collectAsState()
                            val videoFrame by viewModel.latestVideoFrame.collectAsState()
                            val currentMode by viewModel.currentMode.collectAsState()
                            DrivingScreen(
                                connectionState = connectionState,
                                telemetry = telemetry,
                                videoFrame = videoFrame,
                                currentMode = currentMode,
                                onJoystick = viewModel::onJoystick,
                                onEmergencyStop = viewModel::emergencyStop,
                                onSetMode = viewModel::setMode,
                            )
                        }
                        else -> {
                            LockOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
                            val availableCars by viewModel.availableCars.collectAsState()
                            ConnectionScreen(
                                connectionState = connectionState,
                                availableCars = availableCars,
                                onSearch = viewModel::searchCars,
                                onSelectCar = viewModel::selectCar,
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * Une seule Activity pour deux écrans (voir doc de classe) : l'orientation
 * ne peut donc pas se fixer dans le manifest, elle doit suivre l'écran
 * affiché — portrait pour la connexion (formulaire + clavier), paysage pour
 * la conduite (vidéo plein cadre, TODO §Phase 4). `configChanges` dans le
 * manifest couvre l'orientation : ce changement ne recrée pas l'Activity, il
 * ne perturbe donc ni la session ni le ViewModel.
 */
@Composable
private fun LockOrientation(orientation: Int) {
    val activity = LocalContext.current as? Activity ?: return
    DisposableEffect(orientation) {
        activity.requestedOrientation = orientation
        onDispose {}
    }
}
