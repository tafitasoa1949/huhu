# Application mobile — choix techniques, maquette et API

> **Ce document est dépassé pour l'architecture réseau.** L'équipe est
> revenue sur le choix WebSocket direct décrit ci-dessous, au profit de
> l'architecture Gateway + P2P imposée par le sujet — voir
> `docs/mobile-protocol.md`, qui fait foi pour tout ce qui touche au
> protocole app ↔ Gateway ↔ voiture. Les sections encore valables : §3
> (modèle d'états, transposable), §4 (maquettes d'écran), §5 (les cinq
> règles de sécurité, toujours vraies côté Raspberry Pi tant qu'il reste le
> cerveau de décision). Le serveur Raspberry Pi décrit ici (WebSocket) est
> **toujours celui réellement implémenté** dans `vehicle/raspberry-pi/` — ce
> document reste donc exact pour qui travaille sur ce serveur, seule la
> partie mobile en a divergé.

Document de cadrage. L'application mobile est **hors du périmètre du MVP**
(§1.3 du plan de développement, « Application mobile complète » explicitement
reportée). Ce document existe pour que l'équipe décide en connaissance de
cause, et parce que le serveur côté Raspberry Pi, lui, est déjà écrit.

État : le **serveur est implémenté et testé** (`vehicle/raspberry-pi/src/smart_car/api/`).
L'application cliente ne l'est pas — c'est une décision d'équipe.

---

## 1. Choix techniques

### Transport : WebRTC

> **Dépassé.** Le choix ci-dessous (WebRTC, repli MJPEG) a depuis été
> tranché en sens inverse : **MJPEG brut, relayé sans réencodage par le
> Raspberry Pi**, pas de WebRTC du tout. Raison matérielle qui n'était pas
> connue au moment de l'écriture de cette section : le Pi 5 n'a pas
> d'encodeur H.264 matériel (voir l'avertissement plus bas, §Serveur, qui
> lui reste juste), et reproxifier le flux ESP32-CAM tel quel est le choix
> le plus simple et rapide pour un premier prototype qui fonctionne — pas
> la peine de payer le coût d'intégration WebRTC (négociation SDP/ICE) pour
> un bénéfice de latence qui ne se manifeste surtout que sur des liaisons
> avec NAT/Internet, pas en P2P direct sur le même Wi-Fi local. Décision et
> contrat à jour : `docs/architecture.md` (§Décisions tranchées),
> `docs/mobile-protocol.md` (§Flux vidéo). Le reste de cette section (choix
> du serveur, bibliothèques Kotlin) reste informatif mais ne s'applique
> plus à la vidéo.

Le facteur dimensionnant est la **latence**, parce qu'il y a du pilotage
manuel.

| | MJPEG + WebSocket | WebRTC |
|---|---|---|
| Latence vidéo | 250–500 ms | 80–150 ms |
| Bande passante 640×480@25 | 8–15 Mbit/s | 1–2 Mbit/s |
| Adaptation au débit | aucune | contrôle de congestion intégré |
| Canal de contrôle | TCP, blocage de tête de ligne | DataChannel non fiable, UDP |

Le point décisif est le canal de contrôle. Un joystick à 20 Hz produit des
données **périssables** : retransmettre un paquet perdu est nuisible, on
applique une consigne dépassée. En TCP, une perte bloque en plus tous les
paquets suivants — le joystick fige puis rattrape d'un coup. Un DataChannel en
`maxRetransmits: 0` jette le paquet perdu et passe au suivant.

### Serveur : Python + FastAPI (+ aiortc pour le média)

Le serveur doit lire `PerceptionResult` et `DriveCommand` **en mémoire**, dans
le même processus que la décision. Un serveur média séparé imposerait un
second canal pour ressortir ces données.

⚠️ **Le Raspberry Pi 5 n'a plus d'encodeur H.264 matériel** (retiré par rapport
au Pi 4 ; seul le décodage HEVC subsiste). L'encodage sera logiciel. À
640×480 / 25 fps sur les Cortex-A76 c'est quelques pourcents d'un cœur, mais
ne dimensionnez pas en supposant du 1080p accéléré : cela n'existe pas sur
cette carte. Si l'encodage devient limitant, la sortie de secours est
GStreamer + `webrtcbin`.

### Client : Kotlin natif (Android)

Imposé par l'énoncé du projet (§3, « Application mobile → Kotlin (Android) »).
Une première version de ce document envisageait Flutter + `flutter_webrtc`
pour mutualiser l'UI ; ce choix est abandonné, il ne respecte pas le cahier
des charges.

Trois critères techniques, inchangés par rapport à la version précédente :

- **Rendu du HUD** : superposer trajectoire, barres de puissance et
  télémétrie à 60 fps par-dessus la vidéo, avec un contrôle image par image.
- **Entrée** : joystick à retour haptique, verrouillage d'orientation, plein
  écran fiable, manette Bluetooth.
- **Maîtrise de la boucle de rendu**, ce qui compte pour une UI de conduite.

En natif Android, ces trois critères sont satisfaits directement par le SDK
(`View`/`Compose` pour le HUD, `InputDevice`/`MotionEvent` pour le joystick et
la manette), sans dépendre d'un pont vers un moteur de rendu tiers.

**Bibliothèques retenues :**

- **Vidéo WebRTC** : `org.webrtc:google-webrtc`, le binding officiel de
  `libwebrtc` pour Android — la même pile native que celle qu'utiliserait un
  plugin Flutter, sans la couche de pont en plus.
- **Réseau (REST + WebSocket)** : OkHttp (le client WebSocket suffit, pas
  besoin de Retrofit pour une API aussi petite).
- **JSON** : `kotlinx.serialization`, pour mapper les messages du protocole
  décrit en §6 directement sur des `data class` Kotlin.
- **UI** : Jetpack Compose, pour l'overlay HUD par-dessus la surface vidéo et
  la mise à jour à 60 fps sans réinflation de layout.

**Prévoir un repli MJPEG dès la conception.** La négociation WebRTC échoue sur
certains réseaux (WiFi d'établissement avec isolation client). Un chemin
dégradé (simple flux `image/jpeg` affiché dans une `ImageView`/`Image`
Compose) qui marche toujours vaut cher le jour de la démonstration — c'est
d'ailleurs le seul mode que parle l'ESP32-CAM elle-même : ce module n'embarque
aucune pile WebRTC.

### Caméras

⚠️ **Précision d'architecture — il n'y a qu'une seule caméra.** Le Raspberry
Pi n'a pas de caméra CSI/USB qui lui soit propre. La caméra de conduite
**est** l'ESP32-CAM, un module acheté et câblé séparément, relié uniquement
par Wi-Fi (jamais physiquement au Raspberry Pi). Elle sert deux usages à la
fois :

- **Vision (Personne 1)** : le Raspberry Pi lit son flux MJPEG
  (`http://<ip-cam>:81/stream`) pour produire `PerceptionResult` — voir
  `vehicle/esp32-cam/README.md`.
- **Affichage** : le Pi relaie ce même flux, tel quel, à l'écran de conduite
  du téléphone — pas de réencodage WebRTC (décision tranchée depuis,
  voir l'avertissement en tête de §1 et `docs/mobile-protocol.md`,
  §Flux vidéo).

Conséquence directe, qui corrige une version précédente de ce document :
**l'ESP32-CAM parle bien au Raspberry Pi.** Une perte de ce flux n'est donc
plus un simple désagrément d'affichage — c'est une perte de piste
(`lane.detected = false`) que le moteur de décision doit traiter comme telle.
Le trajet ESP32-CAM → Pi est en MJPEG dans tous les cas, la carte n'ayant
pas d'autre pile disponible ; le trajet Pi → téléphone l'est aussi
désormais, le Pi ne faisant que dupliquer le flux sans le réinterpréter.

---

## 2. Architecture

```
                    ┌──WiFi── ESP32-CAM (flux vidéo, caméra de conduite)
                    │
Téléphone ──WiFi──> Raspberry Pi ──USB série──> ESP32 ──> moteurs
                    (décide, arbitre)          (applique, protège)
```

**Le téléphone ne parle jamais directement à l'ESP32.** Deux raisons :

1. Le Pi reçoit le flux caméra (via l'ESP32-CAM) et détient la décision, donc
   ce qu'il y a à afficher.
2. Le pilotage manuel doit emprunter le même `DriveCommand` et le même
   watchdog. Si le téléphone perd le WiFi, le Pi cesse d'émettre et l'ESP32
   coupe en 500 ms. Un raccourci téléphone → ESP32 court-circuiterait toute
   cette sécurité.

Conséquence pratique : **le firmware n'a pas été modifié d'une ligne** pour
supporter le pilotage manuel. Le téléphone est une source de décision de plus,
pas un chemin parallèle.

---

## 3. Modèle d'états

```
        ┌──────────────────────────────────────┐
        │            DISCONNECTED              │
        └──────────────────┬───────────────────┘
                           │ session établie
        ┌──────────────────▼───────────────────┐
        │   IDLE  — moteurs coupés, vidéo ok   │
        └────┬───────────────────────┬─────────┘
             │ « Auto »              │ « Manuel » (appui long 2 s)
        ┌────▼──────┐          ┌─────▼──────┐
        │   AUTO    │◄────────►│   MANUAL   │
        └────┬──────┘          └─────┬──────┘
             └───────────┬───────────┘
                    ┌────▼─────┐
                    │ EMERGENCY│  ← toujours atteignable
                    └────┬─────┘
                         │ acquittement explicite
                      ┌──▼───┐
                      │ IDLE │  ← jamais un retour direct à la conduite
                      └──────┘
```

`AUTO` et `MANUAL` exigent une session pilote active. Un fonctionnement
autonome sans supervision se lance par `smart_car.main`, pas par le serveur :
tant que le serveur pilote, quelqu'un regarde.

---

## 4. Écrans

### Écran 1 — Connexion
Adresse du robot (ou découverte mDNS), état de la liaison, version du firmware.

### Écran 2 — Conduite (paysage, écran principal)

```
┌────────────────────────────────────────────────────────────┐
│ ● LIÉ  42 ms      🔋 82%      [ AUTO │ MANUEL ]      ⛔     │
├────────────────────────────────────────────────────────────┤
│                                                            │
│                 VIDÉO PLEIN CADRE (flux ESP32-CAM)          │
│         ╎          ╎     ← axe de piste détecté            │
│        ╎           ╎                                       │
│                                                            │
│   ┌─────────────────┐                                      │
│   │ TURN_LEFT       │                                      │
│   │ v 30%  dir −30% │                                      │
│   │ conf. 0.91      │                                      │
│   └─────────────────┘                                      │
│   G ███░░░░  +24%          obstacle 1.42 m                 │
│   D ██████░  +58%          ACTIVE · DRIVING                │
└────────────────────────────────────────────────────────────┘
```

L'arrêt d'urgence est **toujours visible**, jamais dans un menu. Les barres par
roue sont la version graphique de `render_wheels()` : c'est le seul endroit où
l'on voit qu'un moteur est inversé.

Quand la liaison se dégrade, l'écran doit **le dire** — image grisée, « liaison
perdue, arrêt dans 0,4 s ». Une vidéo figée sans avertissement est le pire
scénario en manuel.

### Écran 3 — Mode manuel

Passage par **appui long de 2 s**, jamais un simple tap : un basculement
accidentel pendant que la voiture roule est un incident.

Deux joysticks à rappel au centre — gauche la vitesse, droite la direction —
plutôt qu'un seul : le contrôle est plus fin, et on peut relâcher la vitesse
sans perdre le cap.

### Écran 4 — Diagnostic
Télémétrie brute et courbes glissantes : régimes, distance, tension, latence,
taux de commandes refusées.

### Écran 5 — Calibration
Tester chaque moteur séparément, basculer `invert_left` / `invert_right`,
chercher le seuil de démarrage, vérifier que `steering_pct` négatif tourne bien
à gauche. Fait passer la boucle de réglage de deux minutes (éditer, compiler,
téléverser) à deux secondes.

**Le serveur est écrit** : `GET /api/calibration/steps` fournit la procédure
guidée dans l'ordre, avec pour chaque étape l'essai à lancer et le réglage à
ajuster. L'écran n'a qu'à la dérouler. Détails dans `docs/calibration.md`.

### Écran 6 — Rejeu
Relire une session enregistrée, avancer image par image, voir la décision
prise à chaque instant.

---

## 5. Les cinq règles de sécurité

Elles sont **implémentées et testées** dans
`vehicle/raspberry-pi/src/smart_car/api/robot_state.py`. Toute application cliente doit
les considérer comme acquises côté serveur, et ne pas chercher à les
reproduire.

| # | Règle | Où |
|---|---|---|
| 1 | Le client est une entrée non fiable : le bridage est appliqué sur le Pi | `Limits.clamp_*` |
| 2 | Les commandes manuelles périment au bout de 150 ms | `MANUAL_STALE_MS` |
| 3 | Trois filets : 300 ms serveur, 500 ms watchdog ESP32, bouton physique | `PILOT_TIMEOUT_MS` |
| 4 | Passer en manuel remet la vitesse à zéro | `request_mode` |
| 5 | Un seul pilote, les autres en lecture seule | `claim_control` |

L'étagement se constate en direct :

```
en pilotage    : mode=MANUAL    v=40% dir=-60%
silence 200 ms : mode=MANUAL    v=0%     ← règle 2, la consigne a péri
silence 600 ms : mode=IDLE      v=0%     ← règle 3, le pilote est lâché
```

Deux précisions qui comptent :

- **L'ancienneté est mesurée sur l'horloge du Raspberry Pi**, à la réception,
  jamais en comparant l'horodatage du téléphone à l'heure locale : les deux
  horloges ne sont pas synchronisées. L'horodatage client ne sert qu'à ordonner
  les paquets entre eux.
- **Le serveur coupe avant le watchdog** (300 ms contre 500 ms), pour que la
  coupure soit un arrêt commandé et non une panne détectée.

---

## 6. API

Démarrage sans aucun matériel :

```bash
cd vehicle/raspberry-pi
smart-car-server --simulate
```

L'ESP32 virtuel répond, le watchdog se déclenche, les moteurs réagissent.
**L'application mobile peut être développée entièrement sans la voiture.**

Avec la carte réelle : `--port /dev/ttyUSB0`.

### REST

| Méthode | Endpoint | Rôle |
|---|---|---|
| `GET` | `/api/status` | mode, pilote, bridage, dernier instantané |
| `POST` | `/api/session/claim` | demander le pilotage |
| `DELETE` | `/api/session/{id}` | rendre le pilotage |
| `POST` | `/api/mode` | `IDLE` / `AUTO` / `MANUAL` / `EMERGENCY` |
| `POST` | `/api/emergency` | arrêt d'urgence, sans autorisation |
| `POST` | `/api/emergency/clear` | acquitter, retour en `IDLE` |
| `GET` `POST` | `/api/limits` | plafond de vitesse et de direction |

L'arrêt d'urgence existe **sur les deux chemins**, REST et temps réel : un
canal bloqué ne doit pas empêcher d'arrêter la voiture.

### WebSocket

| Chemin | Sens | Rôle |
|---|---|---|
| `/ws/state` | serveur → client | flux d'état, lecture seule, multi-clients |
| `/ws/control?session_id=…` | bidirectionnel | pilotage, une seule session |

Se connecter à `/ws/control` prend le pilotage ; se déconnecter le rend et
immobilise la voiture — c'est le chemin normal quand l'application est fermée
ou le téléphone verrouillé.

**Client → serveur**

```json
{"type":"manual","seq":12,"ts_ms":123456,"speed_pct":30,"steering_pct":-20}
{"type":"heartbeat"}
{"type":"ping","ts_ms":123456}
{"type":"mode","mode":"MANUAL"}
{"type":"emergency"}
```

**Serveur → client**

```json
{"type":"state", ...}
{"type":"mode","accepted":true,"mode":"MANUAL","reason":null}
{"type":"pong","ts_ms":123456,"server_ms":9876}
{"type":"rejected","seq":12,"reason":"STALE"}
```

Une position de joystick acceptée ne produit **aucune réponse** — à 20 Hz, un
acquittement par commande doublerait le trafic pour rien. Seuls les refus sont
signalés, avec leur cause : `NOT_PILOT`, `WRONG_MODE`, `STALE`,
`OUT_OF_ORDER`, `OUT_OF_RANGE`. Un joystick qui ne répond pas sans explication
est indébogable.

`ping` / `pong` renvoie l'horodatage client tel quel : le client calcule son
aller-retour sans supposer les horloges synchronisées. C'est ce qui alimente
l'indicateur de latence.

### Instantané d'état

```json
{
  "mode": "MANUAL",
  "tick_ms": 128340,
  "command": {"sequence": 2567, "action": "TURN_LEFT", "speed_pct": 30,
              "steering_pct": -30, "emergency": false},
  "esp32":   {"status": "OK", "error": null, "obstacle_distance_m": 1.42,
              "battery_pct": 82, "left_rpm": 118.0, "right_rpm": 120.0},
  "lane":    {"detected": true, "error_px": -55.0, "confidence": 0.91},
  "session": {"pilot_connected": true, "max_speed_pct": 40,
              "max_steering_pct": 100}
}
```

Un seul message porte tout ce dont l'écran de conduite a besoin : il n'a jamais
à recomposer un état à partir de sources arrivées à des instants différents.
Le bloc `lane` reste à `null` tant que la Personne 1 n'a pas livré la vision.

---

## 7. Ce qui reste à faire

| Élément | État |
|---|---|
| Arbitrage et règles de sécurité | **fait**, 38 tests |
| Boucle de contrôle 20 Hz | **fait** |
| REST + WebSocket | **fait** |
| Développement sans matériel | **fait** (`--simulate`) |
| Endpoints de calibration | **fait**, 46 tests — voir `docs/calibration.md` |
| Relais vidéo MJPEG côté Pi (`GET /stream`, voir `docs/mobile-protocol.md`) | à faire — remplace l'entrée « Média WebRTC (aiortc) » d'une version précédente de ce tableau, décision changée depuis (§1) |
| Firmware ESP32-CAM (caméra de conduite, MJPEG) | **fait** (`vehicle/esp32-cam/`), cadence/latence à revoir pour un usage continu |
| Application cliente (Kotlin, Android) | **squelette** (`mobile-app/`) — écrans conduite/HUD à finir |

La couche WebRTC ne touchera pas à l'arbitrage : les messages définis ci-dessus
transiteront tels quels par le DataChannel `control`, et les instantanés par
`state`. C'est la raison pour laquelle le transport et les règles ont été
séparés dès le départ.
