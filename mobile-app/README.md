# Application mobile — Kotlin (Android)

Client de pilotage, conformément à l'énoncé (§3, « Application mobile →
Kotlin (Android) »). Architecture **hexagonale (ports & adaptateurs)** :
voir `docs/mobile-protocol.md` pour le protocole Gateway + P2P détaillé.
`docs/mobile-app.md` documente un choix d'équipe antérieur (WebSocket direct
vers le Raspberry Pi, sans Gateway), **abandonné** au profit du sujet —
conservé pour mémoire, plus la source de vérité pour la partie mobile.

## Structure

```
mobile-app/
├── core/    module Kotlin/JVM pur, aucune dépendance Android — se teste
│            avec `gradle :core:test`, sans SDK ni émulateur.
│   domain/       modèles (CarSummary, CarSession, ControlMessage,
│                  TelemetryFrame, ConnectionState) et ports (interfaces) :
│                  GatewayPort, CarControlPort, CarTelemetryPort,
│                  VideoStreamPort.
│   application/   cas d'usage (Discover/Connect/Drive/EmergencyStop/
│                  Disconnect), JoystickMapper, ConnectionWatchdog, et
│                  CarPilotSession — le point d'entrée unique côté UI.
│
└── app/     application Android (Jetpack Compose), dépend de `core`.
    adapter/inbound/ui/    écrans Compose + DrivingViewModel.
    adapter/outbound/gateway/  implémentation REST de GatewayPort (OkHttp).
    adapter/outbound/p2p/      implémentation UDP (contrôle) / TCP
                                (télémétrie) des ports P2P.
    adapter/outbound/video/    implémentation HTTP du relais vidéo MJPEG
                                brut (MjpegVideoStreamAdapter, OkHttp).
    di/AppContainer.kt         racine de composition (pas de framework DI).
```

Même principe de séparation que `vehicle/esp32-controller` : ce qui est pur calcul
et vérifiable sur PC (`core`, ici domaine + application) est isolé de ce qui
dépend de la plateforme (`app`, ici les adaptateurs). L'intérêt de
l'hexagonal par-dessus ce découpage : remplacer un adaptateur (ex. UDP par
un futur transport Wi-Fi Direct) ne touche ni au domaine, ni aux cas
d'usage, ni à l'UI.

## État actuel

Squelette fonctionnel, pas une application terminée :

| Élément | État |
|---|---|
| Domaine + ports (`core/.../domain`) | fait, testé |
| Cas d'usage + `CarPilotSession` (`core/.../application`) | fait, testé |
| `JoystickMapper` (axes -> `speed_pct` [-100, 100] / `steering_pct`) | fait, testé |
| Adaptateur Gateway REST (`GatewayHttpAdapter`) | fait — testé contre le vrai Gateway (`gateway/`, `smart-car-gateway`) |
| Adaptateurs P2P UDP/TCP (`UdpCarControlAdapter`, `TcpCarTelemetryAdapter`) | fait — testé contre le vrai serveur voiture (`vehicle/raspberry-pi/`, `smart-car-server`) |
| Écran 1 — Connexion (Gateway + liste des voitures) | fait |
| Écran 2 — Conduite (joystick, arrêt d'urgence, vidéo en fond plein cadre, jauge de vitesse, batterie/signal, bascule AUTO/MANUAL) | fait |
| Bascule AUTO/MANUAL (`ControlMessage.SetMode`, `docs/mobile-protocol.md` §Commandes) | fait, testé (`SetModeUseCaseTest`) — `mode` est accepté et renvoyé en télémétrie côté voiture, mais aucune boucle de décision autonome n'existe encore derrière `AUTO` |
| Adaptateur vidéo (`MjpegVideoStreamAdapter`) | fait — relais MJPEG brut du Raspberry Pi, décision tranchée (pas de WebRTC : le Pi 5 n'a pas d'encodeur H.264 matériel), voir `docs/architecture.md` §Décisions tranchées et `docs/mobile-protocol.md` §Flux vidéo ; côté voiture, le relais existe (`network/video_relay.py`), testé contre `tools/fake_esp32cam_server.py` en l'absence d'ESP32-CAM réelle |
| Écrans 3 à 6 (diagnostic, calibration, rejeu) | à faire |

**Test de bout en bout** : le serveur Gateway (Phase 1, `gateway/`) et le
côté voiture du protocole P2P (Phase 2, `vehicle/raspberry-pi/src/smart_car/network/`)
existent maintenant et parlent exactement le contrat documenté dans
`docs/mobile-protocol.md`. Le châssis n'est plus piloté par l'ancien
protocole série vers un ESP32-controller (différentiel, `vehicle/esp32-controller/`,
devenu obsolète) : le Raspberry Pi pilote directement un ESC + un servo de
direction en GPIO (`motors/gpio_driver.py`). Reste à faire, hors périmètre
de ce qui a été câblé : la boucle de décision autonome (mode `AUTO`), qui
n'existe encore nulle part dans ce dépôt.

## Compiler et tester

Le module `core` ne nécessite qu'un JDK :

```bash
cd mobile-app
gradle :core:test     # ou ./gradlew une fois le wrapper généré, voir plus bas
```

Le module `app` nécessite le SDK Android (Android Studio le fournit à
l'ouverture du projet). Sans lui, `gradle :app:assembleDebug` échoue à la
résolution du plugin `com.android.application` — c'est pour ça que `core` et
`app` sont deux modules séparés plutôt qu'un seul : on peut travailler sur le
protocole sans installer le SDK.

**Générer le wrapper Gradle** (absent du dépôt : son jar est un binaire, pas
adapté à un premier commit écrit sans réseau) :

```bash
gradle wrapper --gradle-version 8.14.3
```

À faire une fois, depuis un poste avec accès réseau — après ça, `./gradlew`
remplace `gradle` dans toutes les commandes ci-dessus.

## Se connecter à un Gateway et une voiture réels (ou simulés)

```bash
# Terminal 1 — Gateway
cd gateway
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/smart-car-gateway --port 8080

# Terminal 2 — voiture (--simulate tant que l'ESC/servo ne sont pas câblés,
# voir vehicle/raspberry-pi/src/smart_car/config/hardware.py pour les broches)
cd vehicle/raspberry-pi
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/smart-car-server --simulate \
    --ip $(hostname -I | awk '{print $1}') \
    --gateway-url http://<ip-gateway>:8080 \
    --cam-url http://<ip-esp32cam>:81/stream
```

Puis, dans l'app, écran de connexion : IP/port du Gateway → « Rechercher les
voitures » → la voiture apparaît en ligne → « Piloter ». Téléphone et
Raspberry Pi doivent être sur le même réseau Wi-Fi (attention à
l'isolation client, fréquente sur les réseaux d'établissement).

Les tests unitaires de `core` (`GatewayPort`/`CarControlPort`/`CarTelemetryPort`
sont des interfaces, faciles à doubler) restent la référence pour tester le
domaine/application sans réseau du tout.

## Pourquoi Kotlin natif et pas Flutter

Une première version de `docs/mobile-app.md` avait retenu Flutter +
`flutter_webrtc`. Ce choix ne respectait pas l'énoncé du projet et a été
corrigé — le détail des bibliothèques retenues (OkHttp,
kotlinx.serialization, Jetpack Compose) est documenté dans
`docs/mobile-app.md`, §1 « Client : Kotlin natif (Android) ». `google-webrtc`
y est encore cité mais ne s'applique plus : la vidéo est un relais MJPEG
brut sur OkHttp (`adapter/outbound/video/`), décision tranchée depuis (voir
l'avertissement en tête de §1 de ce même document).
