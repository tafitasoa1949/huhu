package com.smartcar.pilot.adapter.inbound.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/**
 * Palette sombre : c'est aussi celle forcée sur l'écran de conduite quel que
 * soit le thème système ([SmartCarTheme]) — la vidéo plein cadre y a besoin
 * de panneaux HUD sombres pour rester lisible sur n'importe quelle scène
 * filmée (adapter/inbound/ui/DrivingScreen.kt, `HudPanel`).
 */
private val SmartCarDarkColorScheme = darkColorScheme(
    primary = Color(0xFF4DD0E1),
    onPrimary = Color(0xFF00363D),
    primaryContainer = Color(0xFF17454C),
    onPrimaryContainer = Color(0xFFB8EAF0),
    secondary = Color(0xFF80CBC4),
    onSecondary = Color(0xFF00332E),
    background = Color(0xFF0B1014),
    onBackground = Color(0xFFE3E8EA),
    surface = Color(0xFF12181D),
    onSurface = Color(0xFFE3E8EA),
    surfaceVariant = Color(0xFF232C33),
    onSurfaceVariant = Color(0xFFC2CBD1),
    outline = Color(0xFF3A444C),
    error = Color(0xFFFF6E6E),
    onError = Color(0xFF3D0B0B),
)

/** Palette claire : utilisée sur l'écran de connexion quand le thème système est clair. */
private val SmartCarLightColorScheme = lightColorScheme(
    primary = Color(0xFF00838F),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFCCE8EA),
    onPrimaryContainer = Color(0xFF002022),
    secondary = Color(0xFF00695C),
    onSecondary = Color(0xFFFFFFFF),
    background = Color(0xFFF5F8F9),
    onBackground = Color(0xFF1A1C1E),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF1A1C1E),
    surfaceVariant = Color(0xFFE4EBED),
    onSurfaceVariant = Color(0xFF45494C),
    outline = Color(0xFFC7CDD0),
    error = Color(0xFFBA1A1A),
    onError = Color(0xFFFFFFFF),
)

val SpeedForwardColor = Color(0xFF4CAF50)
val SpeedReverseColor = Color(0xFFFFA726)
val WarningColor = Color(0xFFFF6E6E)

/**
 * Couleur de contenu pour tout ce qui est peint sur [WarningColor] (bouton
 * d'arrêt d'urgence). Fixe, indépendante du thème clair/sombre : ce fond
 * n'apparaît que sur l'écran de conduite, dont le thème est toujours forcé
 * en sombre ([SmartCarTheme]).
 */
val OnWarningColor = Color(0xFF2A0A0A)

/**
 * `darkTheme` par défaut suit le thème Android (`isSystemInDarkTheme`) : c'est
 * ce qui rend l'écran de connexion clair ou sombre selon le réglage de
 * l'appareil. `MainActivity` force `darkTheme = true` pour l'écran de
 * conduite, indépendamment du système, pour la raison documentée ci-dessus.
 */
@Composable
fun SmartCarTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val colorScheme = if (darkTheme) SmartCarDarkColorScheme else SmartCarLightColorScheme
    MaterialTheme(colorScheme = colorScheme, content = content)
}
