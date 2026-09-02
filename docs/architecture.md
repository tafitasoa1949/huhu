# Architecture générale — Smart RC Car

Synthèse du sujet de projet (SMUAMB06, Université Côte d'Azur — capture LMS
+ `SmartRCCar_Analyse_TODO_Mobile.pdf`). Ce document donne la vue d'ensemble ;
chaque protocole a sa propre référence détaillée, listée en fin de page.

## Trois composants

| Composant | Rôle | Dossier | État |
|---|---|---|---|
| Voiture connectée | Raspberry Pi (décision), caméra ESP32-CAM, ESP32 contrôleur (moteurs/direction), capteurs, batterie LiPo | `vehicle/raspberry-pi/`, `vehicle/esp32-cam/`, `vehicle/esp32-controller/` | partiel — voir §État par composant |
| Gateway | Authentification et association initiale entre l'app et une voiture | *n'existe pas encore dans ce dépôt* | à faire |
| Application mobile | Pilotage FPV, Android ≥ 8.0 (API 26), Kotlin | `mobile-app/` | squelette hexagonal fait, voir `mobile-app/README.md` |

## Architecture réseau — deux phases

```
Phase 1 (REST)          Phase 2 (P2P, le Gateway n'intervient plus)
App ──────► Gateway      App ──UDP (contrôle)──────► Voiture (Raspberry Pi)
     ◄── ip, ports,      App ◄─TCP (télémétrie)────── Voiture
         token           App ◄─HTTP (vidéo, relais MJPEG brut)─ Voiture
```

- **Phase 1 — Association.** L'app interroge le Gateway, obtient l'IP de la
  voiture et un jeton.
- **Phase 2 — Contrôle direct P2P.** L'app communique directement avec la
  voiture en UDP (commandes) / TCP (télémétrie) ; le Gateway n'est plus
  sollicité.

Détail complet des messages, formats JSON et règles de fraîcheur des
paquets : `docs/mobile-protocol.md`.

Sur la voiture, le Raspberry Pi reste celui qui décide et qui parle à
l'ESP32 contrôleur en série (`docs/communication-protocol.md`) : la
Phase 2 change comment le téléphone atteint le Raspberry Pi, pas ce que le
Raspberry Pi fait ensuite avec la commande.

## Exigences non fonctionnelles

| Exigence | Valeur cible |
|---|---|
| Latence de contrôle (commande → réaction) | < 100 ms |
| Latence vidéo | < 200 ms optimal, < 400 ms acceptable |
| Commandes de direction/vitesse | UDP, horodatées, paquets obsolètes ignorés |
| Télémétrie | ≥ 5 mises à jour par seconde |
| Arrêt automatique si perte de connexion | > 2 s |
| Reconnexion automatique côté app | oui |
| Compatibilité Android | ≥ 8.0 (API 26) |

Ces valeurs sont reprises telles quelles par `docs/mobile-protocol.md` côté
protocole app ↔ Gateway ↔ voiture.

## État par composant (vérifié dans le code, pas seulement la doc)

| Composant | État réel |
|---|---|
| Vision (`vehicle/raspberry-pi/src/smart_car/vision/`) | fait, testé (détection de piste ; détection d'obstacle explicitement non implémentée) |
| Décision + sécurité + API réseau côté Raspberry Pi | **n'existe pas** dans ce dépôt (aucune branche) — voir note ci-dessous |
| Communication série Raspberry Pi ↔ ESP32 contrôleur | protocole documenté (`docs/communication-protocol.md`), **implémentation Python absente** ; côté firmware, `vehicle/esp32-controller` l'attend et la teste déjà |
| `vehicle/esp32-controller/` (moteurs, direction, sécurité locale) | fait, testé (44 tests natifs), matériel pas encore monté |
| `vehicle/esp32-cam/` (caméra de conduite, MJPEG) | fait |
| Gateway (association REST) | **n'existe pas** dans ce dépôt |
| `mobile-app/` (Android, hexagonal) | domaine + application + adaptateurs Gateway/P2P/vidéo faits et testés unitairement (relais MJPEG brut, voir §Décisions bloquantes) ; jamais testé contre un vrai Gateway ou une vraie voiture, aucun des deux n'existant encore |

**Note.** Plusieurs documents de ce dossier (`mobile-app.md`,
`communication-protocol.md`) décrivent une couche décision/sécurité/API
Raspberry Pi comme « implémentée et testée » (CLI `smart_car`, serveur,
simulateur ESP32, une centaine de tests). Cette couche n'a été retrouvée
dans aucune branche du dépôt au moment de la rédaction de ce document — à
vérifier auprès de l'équipe avant de considérer ces sections comme
descriptives de l'état réel plutôt que comme plan cible.

## Décisions bloquantes

- **Implémentation du Gateway et de la couche décision/API côté voiture** —
  aucun des deux composants n'existe encore ; sans eux, ni l'app mobile ni
  `vehicle/esp32-controller` ne peuvent être pilotés en conditions réelles.
  C'est aussi ce qui bloque le relais vidéo (`GET /stream`, voir
  `docs/mobile-protocol.md`) : il doit vivre dans cette même couche, côté
  Raspberry Pi.

## Décisions tranchées

- **Technologie de streaming vidéo : MJPEG brut, relayé sans réencodage par
  le Raspberry Pi.** Ni WebRTC, ni GStreamer. Raison matérielle : le **Pi 5
  n'a pas d'encodeur H.264 matériel** (retiré par rapport au Pi 4 ; seul le
  décodage HEVC subsiste), et l'unique caméra du véhicule est l'ESP32-CAM,
  qui ne sait de toute façon parler que MJPEG — un réencodage côté Pi
  coûterait du CPU logiciel pour rien. Reproxifier le flux tel quel
  (octet pour octet) est le choix le plus simple et le plus rapide à mettre
  en œuvre pour un premier prototype qui fonctionne ; un passage à un
  encodage plus économe en bande passante (H.264 logiciel via GStreamer)
  reste une optimisation possible plus tard si la bande passante Wi-Fi
  Pi → téléphone s'avère limitante en pratique, pas un prérequis. Détail du
  contrat HTTP : `docs/mobile-protocol.md`, §Flux vidéo. Côté app, le port
  est implémenté (`MjpegVideoStreamAdapter`), voir §État par composant
  ci-dessus.

## Références détaillées

| Sujet | Document |
|---|---|
| Protocole app ↔ Gateway ↔ voiture (Phase 1 REST, Phase 2 P2P) | `docs/mobile-protocol.md` |
| Ancien choix (WebSocket direct, abandonné) | `docs/mobile-app.md` |
| Protocole série Raspberry Pi ↔ ESP32 contrôleur | `docs/communication-protocol.md` |
| Contrats vision → décision → contrôle | `docs/contracts.md` |
| Calibration du châssis | `docs/calibration.md` |
| Suivi des tâches | `docs/tasks.md` |
