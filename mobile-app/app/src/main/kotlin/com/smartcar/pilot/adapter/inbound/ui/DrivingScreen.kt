package com.smartcar.pilot.adapter.inbound.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Fill
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import com.smartcar.pilot.domain.model.ConnectionState
import com.smartcar.pilot.domain.model.DrivingMode
import com.smartcar.pilot.domain.model.TelemetryFrame
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/**
 * Écran 2 (PDF §Phase 3) : conduite. Vidéo plein cadre en fond
 * ([VideoBackground] — relais MJPEG brut, décision tranchée, voir
 * docs/architecture.md), panneaux HUD semi-transparents par-dessus pour
 * rester lisible quelle que soit la scène filmée : statut de liaison, mode
 * AUTO/MANUEL, batterie, signal, jauge de vitesse, joysticks, arrêt
 * d'urgence toujours visible (PDF §Phase 5, exigence ergonomie 4.4).
 */
@Composable
fun DrivingScreen(
    connectionState: ConnectionState,
    telemetry: TelemetryFrame?,
    videoFrame: ByteArray?,
    currentMode: DrivingMode,
    onJoystick: (throttle: Float, steering: Float) -> Unit,
    onEmergencyStop: () -> Unit,
    onSetMode: (DrivingMode) -> Unit,
) {
    var throttle by remember { mutableFloatStateOf(0f) }
    var steering by remember { mutableFloatStateOf(0f) }

    // 20 Hz en continu tant que la session est ouverte, joystick centré
    // inclus (docs/mobile-protocol.md) : c'est ce flux régulier qui tient
    // lieu de maintien de liaison, et qui permet une reconnexion automatique
    // si la voiture recommence à recevoir après une coupure (LinkLost).
    LaunchedEffect(connectionState) {
        while (connectionState is ConnectionState.Connected || connectionState is ConnectionState.LinkLost) {
            onJoystick(throttle, steering)
            delay(50)
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        VideoBackground(videoFrame)

        Column(
            modifier = Modifier.fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            HudPanel { StatusBar(connectionState, telemetry, currentMode, onSetMode) }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Bottom,
            ) {
                Joystick(
                    label = "Vitesse",
                    orientation = JoystickOrientation.VERTICAL,
                    onAxisChanged = { throttle = it },
                )

                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    HudPanel { SpeedGauge(telemetry?.speedPct) }
                    Spacer(Modifier.height(12.dp))
                    Button(
                        onClick = onEmergencyStop,
                        colors = ButtonDefaults.buttonColors(containerColor = WarningColor, contentColor = OnWarningColor),
                        modifier = Modifier.height(56.dp),
                        shape = RoundedCornerShape(14.dp),
                    ) {
                        StopIcon(tint = OnWarningColor, modifier = Modifier.size(20.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("ARRÊT D'URGENCE", style = MaterialTheme.typography.titleMedium)
                    }
                }

                Joystick(
                    label = "Direction",
                    orientation = JoystickOrientation.HORIZONTAL,
                    onAxisChanged = { steering = it },
                )
            }
        }
    }
}

/** Panneau semi-transparent commun à tous les blocs HUD : lisible sur n'importe quelle scène filmée. */
@Composable
private fun HudPanel(content: @Composable () -> Unit) {
    Surface(
        color = Color.Black.copy(alpha = 0.55f),
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.border(1.dp, Color.White.copy(alpha = 0.10f), RoundedCornerShape(16.dp)),
    ) {
        Box(modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp)) { content() }
    }
}

/**
 * Décode chaque JPEG reçu du relais MJPEG en arrière-plan (le décodage
 * bitmap n'a rien à faire sur le thread UI) et affiche la dernière frame
 * disponible en plein cadre. Reste vide (fond du thème) tant qu'aucune
 * frame n'est encore arrivée — pas d'image cassée à l'ouverture de l'écran.
 */
@Composable
private fun VideoBackground(videoFrame: ByteArray?) {
    var bitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }

    LaunchedEffect(videoFrame) {
        if (videoFrame == null) return@LaunchedEffect
        bitmap = withContext(Dispatchers.Default) {
            BitmapFactory.decodeByteArray(videoFrame, 0, videoFrame.size)
        }
    }

    bitmap?.let {
        Image(
            bitmap = it.asImageBitmap(),
            contentDescription = "Flux vidéo FPV",
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop,
        )
    }
}

@Composable
private fun StatusBar(
    connectionState: ConnectionState,
    telemetry: TelemetryFrame?,
    currentMode: DrivingMode,
    onSetMode: (DrivingMode) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        ConnectionPill(connectionState)
        ModeToggle(currentMode = currentMode, onSetMode = onSetMode)
        Row(verticalAlignment = Alignment.CenterVertically) {
            BatteryIndicator(telemetry?.batteryPct)
            Spacer(Modifier.width(16.dp))
            SignalIndicator(telemetry?.rssiDbm)
        }
    }
}

@Composable
private fun ConnectionPill(connectionState: ConnectionState) {
    val (dotColor, label) = when (connectionState) {
        ConnectionState.Connected -> SpeedForwardColor to "LIÉ"
        ConnectionState.LinkLost -> WarningColor to "LIAISON PERDUE"
        is ConnectionState.Failed -> WarningColor to "ÉCHEC : ${connectionState.reason}"
        ConnectionState.Associating -> MaterialTheme.colorScheme.onSurfaceVariant to "ASSOCIATION..."
        ConnectionState.Discovering -> MaterialTheme.colorScheme.onSurfaceVariant to "RECHERCHE..."
        ConnectionState.Disconnected -> MaterialTheme.colorScheme.onSurfaceVariant to "DÉCONNECTÉ"
        ConnectionState.Idle -> MaterialTheme.colorScheme.onSurfaceVariant to "INACTIF"
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(dotColor),
        )
        Spacer(Modifier.width(8.dp))
        Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurface)
    }
}

/**
 * Bascule AUTO/MANUAL (docs/mobile-app.md, §3 — état sous supervision d'une
 * session pilote active). Deux boutons plutôt qu'un `SegmentedButton`
 * Material3 (encore expérimental dans la version de compose-bom utilisée
 * ici) : même rendu « à onglets », sans dépendance instable.
 */
@Composable
private fun ModeToggle(currentMode: DrivingMode, onSetMode: (DrivingMode) -> Unit) {
    Row {
        ModeButton("AUTO", selected = currentMode == DrivingMode.AUTO) { onSetMode(DrivingMode.AUTO) }
        Spacer(Modifier.width(4.dp))
        ModeButton("MANUEL", selected = currentMode == DrivingMode.MANUAL) { onSetMode(DrivingMode.MANUAL) }
    }
}

@Composable
private fun ModeButton(label: String, selected: Boolean, onClick: () -> Unit) {
    if (selected) {
        Button(onClick = onClick, contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium)
        }
    } else {
        OutlinedButton(onClick = onClick, contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium)
        }
    }
}

/** Seuil d'alerte bas (PDF §Phase 5) : rouge sous 20 %, couleur normale sinon. */
@Composable
private fun BatteryIndicator(batteryPct: Int?) {
    val color = if (batteryPct != null && batteryPct < 20) WarningColor else MaterialTheme.colorScheme.onSurface
    Row(verticalAlignment = Alignment.CenterVertically) {
        BatteryIcon(pct = batteryPct, tint = color, modifier = Modifier.size(width = 22.dp, height = 14.dp))
        Spacer(Modifier.width(6.dp))
        Text(
            batteryPct?.let { "$it%" } ?: "--",
            color = color,
            style = MaterialTheme.typography.labelLarge,
        )
    }
}

/** Qualité de signal Wi-Fi (PDF §Phase 5) : trois paliers approximatifs sur le RSSI, pas de norme unique. */
@Composable
private fun SignalIndicator(rssiDbm: Int?) {
    val (bars, color) = when {
        rssiDbm == null -> 0 to MaterialTheme.colorScheme.onSurfaceVariant
        rssiDbm >= -60 -> 3 to SpeedForwardColor
        rssiDbm >= -75 -> 2 to SpeedReverseColor
        else -> 1 to WarningColor
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        SignalIcon(
            filledBars = bars,
            tint = color,
            dimTint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.35f),
            modifier = Modifier.size(width = 20.dp, height = 14.dp),
        )
        Spacer(Modifier.width(6.dp))
        Text(
            rssiDbm?.let { "$it dBm" } ?: "--",
            color = color,
            style = MaterialTheme.typography.labelLarge,
        )
    }
}

/** Icône batterie vectorielle : corps + plot, remplissage proportionnel au niveau. Remplace l'emoji 🔋. */
@Composable
private fun BatteryIcon(pct: Int?, tint: Color, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height
        val bodyRight = w * 0.84f
        val strokeWidth = h * 0.12f

        drawRoundRect(
            color = tint,
            topLeft = Offset(0f, 0f),
            size = Size(bodyRight, h),
            cornerRadius = CornerRadius(h * 0.22f),
            style = Stroke(width = strokeWidth),
        )
        drawRoundRect(
            color = tint,
            topLeft = Offset(bodyRight + w * 0.03f, h * 0.28f),
            size = Size(w * 0.12f, h * 0.44f),
            cornerRadius = CornerRadius(h * 0.08f),
        )

        val fraction = ((pct ?: 0) / 100f).coerceIn(0f, 1f)
        val inset = strokeWidth * 1.3f
        val fillWidth = (bodyRight - inset * 2) * fraction
        if (fillWidth > 0f) {
            drawRoundRect(
                color = tint,
                topLeft = Offset(inset, inset),
                size = Size(fillWidth, h - inset * 2),
                cornerRadius = CornerRadius(h * 0.10f),
                style = Fill,
            )
        }
    }
}

/** Icône de signal vectorielle : trois barres croissantes, remplace l'emoji 📶. */
@Composable
private fun SignalIcon(filledBars: Int, tint: Color, dimTint: Color, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height
        val barWidth = w / 4.4f
        val gap = w * 0.12f
        val barHeights = listOf(h * 0.40f, h * 0.68f, h)

        barHeights.forEachIndexed { index, barHeight ->
            val x = index * (barWidth + gap)
            drawRoundRect(
                color = if (index < filledBars) tint else dimTint,
                topLeft = Offset(x, h - barHeight),
                size = Size(barWidth, barHeight),
                cornerRadius = CornerRadius(barWidth * 0.3f),
            )
        }
    }
}

/** Icône octogonale « stop », remplace l'emoji ⛔ sur le bouton d'arrêt d'urgence. */
@Composable
private fun StopIcon(tint: Color, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier) { drawStopOctagon(tint) }
}

private fun DrawScope.drawStopOctagon(tint: Color) {
    val w = size.width
    val h = size.height
    val cut = w * 0.30f

    val octagon = Path().apply {
        moveTo(cut, 0f)
        lineTo(w - cut, 0f)
        lineTo(w, h * 0.30f)
        lineTo(w, h * 0.70f)
        lineTo(w - cut, h)
        lineTo(cut, h)
        lineTo(0f, h * 0.70f)
        lineTo(0f, h * 0.30f)
        close()
    }
    drawPath(octagon, color = tint, style = Fill)

    drawRoundRect(
        color = Color.Black.copy(alpha = 0.55f),
        topLeft = Offset(w * 0.24f, h * 0.44f),
        size = Size(w * 0.52f, h * 0.12f),
        cornerRadius = CornerRadius(h * 0.06f),
    )
}

/**
 * Jauge de vitesse (PDF §Phase 5) : barre bidirectionnelle centrée sur 0 —
 * `speedPct` va de -100 (marche arrière) à +100 (PDF §Phase 3), donc une
 * simple barre 0..100 mentirait sur le sens de marche.
 */
@Composable
private fun SpeedGauge(speedPct: Int?) {
    val value = speedPct ?: 0
    val fraction = (kotlin.math.abs(value) / 100f).coerceIn(0f, 1f)
    val barColor = if (value < 0) SpeedReverseColor else SpeedForwardColor

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            speedPct?.let { "$it%" } ?: "--",
            style = MaterialTheme.typography.headlineSmall,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Text(
            if (value < 0) "MARCHE ARRIÈRE" else "AVANT",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(6.dp))
        Box(
            modifier = Modifier
                .width(160.dp)
                .height(8.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(fraction)
                    .height(8.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(barColor),
            )
            Box(
                modifier = Modifier
                    .width(2.dp)
                    .height(8.dp)
                    .align(Alignment.Center)
                    .background(Color.Black.copy(alpha = 0.35f)),
            )
        }
    }
}
