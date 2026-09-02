package com.smartcar.pilot.adapter.inbound.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Fill
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.smartcar.pilot.domain.model.CarSummary
import com.smartcar.pilot.domain.model.ConnectionState

/**
 * Écran 1 (PDF §Phase 1) : d'abord l'adresse du Gateway (§Phase 0, aucune
 * découverte automatique — pas de justification à en ajouter une tant que
 * la démonstration se fait sur un réseau connu), puis la liste des voitures
 * qu'il expose.
 */
@Composable
fun ConnectionScreen(
    connectionState: ConnectionState,
    availableCars: List<CarSummary>,
    onSearch: (host: String, port: Int) -> Unit,
    onSelectCar: (carId: String) -> Unit,
) {
    var gatewayHost by remember { mutableStateOf("192.168.1.10") }
    var gatewayPortText by remember { mutableStateOf("8080") }

    // Défilable : portrait ou paysage, clavier ouvert ou non, le bouton et la
    // liste des voitures doivent toujours rester atteignables plutôt que
    // coupés hors de l'écran visible (bug observé : rien d'utilisable après
    // avoir rempli les champs, le clavier poussait tout le reste hors cadre).
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(
                        MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.55f),
                        MaterialTheme.colorScheme.background,
                    ),
                ),
            )
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(32.dp))
        Branding()
        Spacer(Modifier.height(32.dp))

        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 3.dp),
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    "Connexion au Gateway",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    "Renseignez l'adresse du boîtier relié à la voiture.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(20.dp))
                OutlinedTextField(
                    value = gatewayHost,
                    onValueChange = { gatewayHost = it },
                    label = { Text("Adresse du Gateway") },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = gatewayPortText,
                    onValueChange = { gatewayPortText = it.filter(Char::isDigit) },
                    label = { Text("Port du Gateway") },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(20.dp))
                Button(
                    onClick = { gatewayPortText.toIntOrNull()?.let { onSearch(gatewayHost, it) } },
                    enabled = gatewayHost.isNotBlank() && gatewayPortText.toIntOrNull() != null,
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    shape = RoundedCornerShape(12.dp),
                ) {
                    Text("Rechercher les voitures", fontWeight = FontWeight.SemiBold)
                }
            }
        }

        Spacer(Modifier.height(24.dp))

        when (connectionState) {
            is ConnectionState.Discovering -> CircularProgressIndicator()
            is ConnectionState.Failed -> ErrorBanner(connectionState.reason)
            else -> Unit
        }

        if (availableCars.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text(
                "Voitures disponibles",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
            )
        }

        // Boucle simple, pas de LazyColumn : imbriquer une liste paresseuse
        // dans un Column défilant (verticalScroll ci-dessus) plante au
        // rendu (hauteur infinie) — sans intérêt de toute façon pour la
        // poignée de voitures que ce Gateway a réellement à lister.
        Column(modifier = Modifier.fillMaxWidth()) {
            availableCars.forEach { car ->
                CarRow(car = car, onSelect = { onSelectCar(car.carId) })
                Spacer(Modifier.height(8.dp))
            }
        }

        if (connectionState == ConnectionState.Idle && availableCars.isEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text(
                "Aucune voiture trouvée pour l'instant.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun Branding() {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            modifier = Modifier
                .size(84.dp)
                .clip(CircleShape)
                .background(
                    Brush.linearGradient(
                        colors = listOf(
                            MaterialTheme.colorScheme.primary,
                            MaterialTheme.colorScheme.secondary,
                        ),
                    ),
                ),
            contentAlignment = Alignment.Center,
        ) {
            CarIcon(
                tint = MaterialTheme.colorScheme.onPrimary,
                modifier = Modifier.size(44.dp),
            )
        }
        Spacer(Modifier.height(16.dp))
        Text(
            "Smart Car Pilot",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        Text(
            "Pilotage immersif FPV",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * Icône voiture dessinée en vectoriel (silhouette + roues), pas une image ni
 * un emoji : rendu net et cohérent avec la teinte du thème à n'importe quelle
 * taille et sur les deux modes clair/sombre.
 */
@Composable
private fun CarIcon(modifier: Modifier = Modifier, tint: androidx.compose.ui.graphics.Color) {
    Canvas(modifier = modifier) { drawCarSilhouette(tint) }
}

private fun DrawScope.drawCarSilhouette(tint: androidx.compose.ui.graphics.Color) {
    val w = size.width
    val h = size.height

    val body = Path().apply {
        addRoundRect(
            androidx.compose.ui.geometry.RoundRect(
                left = w * 0.06f,
                top = h * 0.50f,
                right = w * 0.94f,
                bottom = h * 0.72f,
                cornerRadius = CornerRadius(h * 0.10f, h * 0.10f),
            ),
        )
    }
    val cabin = Path().apply {
        addRoundRect(
            androidx.compose.ui.geometry.RoundRect(
                left = w * 0.26f,
                top = h * 0.28f,
                right = w * 0.74f,
                bottom = h * 0.56f,
                topLeftCornerRadius = CornerRadius(w * 0.16f, w * 0.16f),
                topRightCornerRadius = CornerRadius(w * 0.16f, w * 0.16f),
                bottomLeftCornerRadius = CornerRadius(0f, 0f),
                bottomRightCornerRadius = CornerRadius(0f, 0f),
            ),
        )
    }

    drawPath(body, color = tint, style = Fill)
    drawPath(cabin, color = tint, style = Fill)

    val wheelRadius = w * 0.12f
    val wheelY = h * 0.74f
    listOf(w * 0.26f, w * 0.74f).forEach { wheelX ->
        drawCircle(color = tint.copy(alpha = 0.35f), radius = wheelRadius, center = androidx.compose.ui.geometry.Offset(wheelX, wheelY))
        drawCircle(color = tint, radius = wheelRadius * 0.5f, center = androidx.compose.ui.geometry.Offset(wheelX, wheelY))
    }
}

@Composable
private fun ErrorBanner(reason: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = WarningColor.copy(alpha = 0.15f)),
    ) {
        Text(
            "Erreur : $reason",
            modifier = Modifier.padding(12.dp),
            color = WarningColor,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun CarRow(car: CarSummary, onSelect: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .clip(CircleShape)
                        .background(if (car.online) SpeedForwardColor else MaterialTheme.colorScheme.onSurfaceVariant),
                )
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(car.name, style = MaterialTheme.typography.titleMedium)
                    Text(
                        if (car.online) "en ligne" else "hors ligne",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Button(onClick = onSelect, enabled = car.online, shape = RoundedCornerShape(12.dp)) {
                Text("Piloter")
            }
        }
    }
}
