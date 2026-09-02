# Suivi des tâches

Repris de `SmartRCCar_Analyse_TODO_Mobile.pdf` (26 août 2026), complété par
l'état réel du code au moment de la rédaction. Voir `docs/architecture.md`
pour la vue d'ensemble.

## Application mobile (Android / Kotlin)

| Phase | Contenu | État |
|---|---|---|
| 0 — Setup & architecture | Projet Android Studio, architecture, modules, Git, permissions manifest | **fait** — architecture hexagonale (`domain`/`application`/`adapter`), voir `mobile-app/README.md` |
| 1 — Connexion au Gateway (APP-07) | Écran connexion, client HTTP, récupération IP/token, gestion d'erreurs | **fait** côté app (`GatewayHttpAdapter`, `ConnectionScreen`) — **jamais testé contre un vrai Gateway, qui n'existe pas** |
| 2 — Bascule en mode P2P (APP-08) | Socket UDP contrôle, socket TCP télémétrie, séquence/horodatage, watchdog, arrêt d'urgence | **fait** côté app (`UdpCarControlAdapter`, `TcpCarTelemetryAdapter`, `ConnectionWatchdog`) — même réserve, aucune voiture ne parle ce protocole |
| 3 — Contrôles de pilotage (APP-02, APP-03) | Direction (gyroscope ou joystick), accélération/frein, mapping -100..100 %, limitation de fréquence | **fait** — joystick virtuel choisi (pas de gyroscope) ; limitation à 20 Hz |
| 4 — Flux vidéo FPV (APP-01) | Relais MJPEG brut (décision tranchée, voir `docs/architecture.md`), lecteur vidéo, plein écran, reconnexion indépendante | **fait** côté app — `MjpegVideoStreamAdapter` (HTTP, reparsing multipart), `VideoStreamPort` câblé dans `ConnectToCarUseCase`/`DisconnectUseCase`, affichage plein cadre dans `DrivingScreen` ; même réserve que Phase 1/2 : rien en face pour tester en conditions réelles (relais côté Raspberry Pi pas encore écrit, voir §Hors périmètre) |
| 5 — Télémétrie & tableau de bord (APP-04, APP-05, APP-06) | Écouteur télémétrie ≥ 5 Hz, StateFlow, jauges vitesse/batterie/signal | **partiel** — trames reçues et exposées (`TelemetryFrame`), affichage texte simple ; pas de jauges graphiques, pas de superposition sur la vidéo (dépend de la Phase 4) |
| 6 — Tests & robustesse | Tests parsing réseau, coupure Wi-Fi, latence réelle, Android 8.0 | **partiel** — tests unitaires du domaine/application (mapper, watchdog, cas d'usage) faits ; tests de coupure réelle et de latence impossibles tant qu'il n'y a rien en face (voir Gateway/voiture ci-dessous) |
| 7 — Documentation | README module, protocole applicatif partagé | **fait** — `mobile-app/README.md`, `docs/mobile-protocol.md` |

## Décisions bloquantes (mobile)

- **Format exact des paquets** (contrôle/télémétrie/vidéo) — tranché côté
  app dans `docs/mobile-protocol.md`, à valider par l'équipe qui
  implémentera le Gateway et la voiture.

Technologie de streaming vidéo : **tranchée** (MJPEG brut relayé par le
Raspberry Pi, sans réencodage — le Pi 5 n'a pas d'encodeur H.264 matériel).
Voir `docs/architecture.md`, §Décisions tranchées.

## Hors périmètre mobile — prérequis pour un test de bout en bout

Aucune des deux tâches suivantes n'appartient à l'app mobile, mais sans
elles l'app ne peut être essayée qu'en tests unitaires, jamais en
conditions réelles (voir `docs/architecture.md`, §État par composant) :

- [ ] **Gateway** (Phase 1, REST) — service `GET /api/cars` /
  `POST /api/cars/{id}/claim`, à choisir en Python/Node.js/Spring Boot.
  N'existe pas dans ce dépôt.
- [ ] **Couche décision + sécurité + réseau côté Raspberry Pi** — reçoit les
  commandes UDP, arbitre, parle en série à `vehicle/esp32-controller`, publie la
  télémétrie en TCP, **et relaie la vidéo** (`GET /stream`, MJPEG brut
  reproxifié depuis l'ESP32-CAM — voir `docs/mobile-protocol.md`,
  §Flux vidéo). Seule la vision (`vehicle/raspberry-pi/src/smart_car/vision/`)
  est implémentée à ce jour ; le reste (décision, sécurité, CLI, serveur,
  simulateur, relais vidéo) décrit dans `docs/mobile-app.md` et
  `docs/communication-protocol.md` n'a été retrouvé dans aucune branche du
  dépôt.

## Autres composants (rappel — pas de tâche ouverte)

- `vehicle/esp32-controller/` : firmware moteurs/direction fait et testé,
  matériel pas encore monté.
- `vehicle/esp32-cam/` : firmware caméra fait.
