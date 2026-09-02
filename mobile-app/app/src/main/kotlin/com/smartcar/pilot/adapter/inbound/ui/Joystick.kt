package com.smartcar.pilot.adapter.inbound.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.roundToInt
import kotlin.math.sin

enum class JoystickOrientation { VERTICAL, HORIZONTAL }

/**
 * Joystick à rappel au centre (PDF §Phase 3) : relâcher le doigt doit
 * vouloir dire vitesse et direction nulles, jamais "garder la dernière
 * valeur envoyée" — un manche qui reste bloqué à fond après un lâcher
 * accidentel serait dangereux.
 *
 * `orientation` choisit l'axe qui compte : VERTICAL pour la vitesse (haut =
 * plein gaz, bas = marche arrière — VH-02), HORIZONTAL pour la direction
 * (droite = positif, conforme à la convention gauche négative / droite
 * positive de docs/contracts.md).
 */
@Composable
fun Joystick(
    label: String,
    orientation: JoystickOrientation,
    onAxisChanged: (Float) -> Unit,
) {
    val sizeDp = 140.dp
    val knobSizeDp = 48.dp
    var knobOffset by remember { mutableStateOf(Offset.Zero) }
    val radiusPx = with(LocalDensity.current) { (sizeDp / 2).toPx() }
    val haptics = LocalHapticFeedback.current

    fun axisFor(offset: Offset): Float = when (orientation) {
        JoystickOrientation.VERTICAL -> (-offset.y / radiusPx).coerceIn(-1f, 1f)
        JoystickOrientation.HORIZONTAL -> (offset.x / radiusPx).coerceIn(-1f, 1f)
    }

    fun release() {
        knobOffset = Offset.Zero
        onAxisChanged(0f)
    }

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            label,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center,
            color = Color.White,
        )
        Spacer(Modifier.height(8.dp))
        Box(
            modifier = Modifier
                .size(sizeDp)
                .shadow(elevation = 6.dp, shape = CircleShape, clip = false)
                .clip(CircleShape)
                .background(
                    Brush.radialGradient(
                        colors = listOf(
                            MaterialTheme.colorScheme.surfaceVariant,
                            MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.75f),
                        ),
                    ),
                )
                .border(1.dp, Color.White.copy(alpha = 0.12f), CircleShape)
                .pointerInput(orientation) {
                    detectDragGestures(
                        onDragStart = {
                            haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                        },
                        onDrag = { change, dragAmount ->
                            change.consume()
                            val proposed = knobOffset + dragAmount
                            val distance = hypot(proposed.x, proposed.y)
                            knobOffset = if (distance > radiusPx) {
                                val angle = atan2(proposed.y, proposed.x)
                                Offset(radiusPx * cos(angle), radiusPx * sin(angle))
                            } else {
                                proposed
                            }
                            onAxisChanged(axisFor(knobOffset))
                        },
                        onDragEnd = { release() },
                        onDragCancel = { release() },
                    )
                },
            contentAlignment = Alignment.Center,
        ) {
            // Repère central : rappelle visuellement le point de rappel (relâcher = 0).
            Box(
                modifier = Modifier
                    .size(4.dp)
                    .clip(CircleShape)
                    .background(Color.White.copy(alpha = 0.25f)),
            )
            Box(
                modifier = Modifier
                    .offset {
                        IntOffset(knobOffset.x.roundToInt(), knobOffset.y.roundToInt())
                    }
                    .size(knobSizeDp)
                    .shadow(elevation = 4.dp, shape = CircleShape, clip = false)
                    .clip(CircleShape)
                    .background(
                        Brush.radialGradient(
                            colors = listOf(
                                MaterialTheme.colorScheme.primary,
                                MaterialTheme.colorScheme.secondary,
                            ),
                        ),
                    ),
            )
        }
    }
}
