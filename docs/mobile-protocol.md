# Protocole application mobile — Gateway & P2P

Ce document remplace, pour la partie application mobile, l'architecture
décrite dans `docs/mobile-app.md` (WebSocket direct vers le Raspberry Pi).

> **Pourquoi ce changement.** Le sujet de projet (SMUAMB06) impose une
> architecture en deux phases : un serveur Gateway pour l'association, puis
> un pilotage en direct (P2P) entre le téléphone et la voiture, en UDP/TCP.
> `docs/mobile-app.md` documentait un choix d'équipe antérieur (WebSocket
> unique vers le Raspberry Pi, sans Gateway) — ce choix est abandonné au
> profit du sujet. **Aucun serveur Gateway n'existe encore dans ce dépôt** ;
> ce document sert de contrat à implémenter côté embarqué/gateway, au même
> titre que `docs/contracts.md` pour la vision/décision.

Les conventions de nommage reprennent celles de `docs/contracts.md`
(`_pct`, `_ms`, `_m`, `_dbm`, gauche négatif / droite positif, valeur
inconnue = `null` jamais `0`), pour qu'un même vocabulaire traverse tout le
projet.

Exigences non fonctionnelles complètes (latence, Android minimum...) :
`docs/architecture.md`, §Exigences non fonctionnelles. Ce document-ci ne
reprend que celles qui contraignent directement le format des paquets
(fraîcheur, cadence, timeout de liaison).

---

## Phase 1 — Association (Gateway, REST)

Le Gateway est un service HTTP (Python/Node.js/Spring Boot — au choix de
l'équipe qui l'implémente) qui connaît les voitures en ligne sur le réseau
et arbitre leur association à un pilote.

### `GET /api/cars`

Liste les voitures actuellement joignables.

```json
[
  {"car_id": "car-01", "name": "Smart RC Car #1", "online": true}
]
```

### `POST /api/cars/{car_id}/claim`

Demande le pilotage d'une voiture. Le Gateway répond avec l'adresse directe
de la voiture et un jeton à présenter en Phase 2 — le Gateway n'intervient
plus après cet appel.

Réponse `200` :

```json
{
  "car_id": "car-01",
  "ip": "192.168.4.23",
  "control_port": 5005,
  "telemetry_port": 5006,
  "video_port": 5007,
  "token": "3f7a1c2e-...",
  "expires_in_s": 30
}
```

`video_port` : port HTTP sur lequel le Raspberry Pi relaie la vidéo (voir
§Flux vidéo ci-dessous) — jamais le port de l'ESP32-CAM elle-même, que le
téléphone n'atteint pas directement.

`expires_in_s` : durée pendant laquelle le token est valable côté voiture
s'il n'y a pas de trafic — la voiture doit rejeter les paquets P2P (Phase 2)
présentant un token expiré ou inconnu.

Réponse `409` si la voiture est déjà revendiquée par un autre pilote.

---

## Phase 2 — Contrôle direct P2P

Une fois le token obtenu, **le Gateway n'est plus dans la boucle**. L'app
parle directement à `ip:control_port` (UDP) et `ip:telemetry_port` (TCP).

### Commandes — UDP, app → voiture

Une ligne JSON par paquet, envoyée **en continu à 20 Hz tant que la session
est ouverte** — y compris joystick au centre (`speed_pct: 0, steering_pct: 0`).
C'est volontairement le flux continu qui sert de maintien de liaison : pas de
message `heartbeat` séparé, un centrage du joystick n'est pas une raison de
cesser d'émettre. Canal non fiable et non ordonné par construction : chaque
paquet porte son propre numéro de séquence et son horodatage.

```json
{"type":"drive","token":"3f7a1c2e-...","seq":128,"ts_ms":1699999999000,"speed_pct":42,"steering_pct":-15}
{"type":"emergency","token":"3f7a1c2e-...","seq":129,"ts_ms":1699999999050}
{"type":"mode","token":"3f7a1c2e-...","seq":130,"ts_ms":1699999999100,"mode":"AUTO"}
```

| Champ | Type | Règle |
|---|---|---|
| `speed_pct` | int | **-100 à +100** (marche arrière possible en pilotage manuel direct — diffère volontairement de `docs/contracts.md`, qui borne à [0, 100] pour la conduite autonome via le Raspberry Pi) |
| `steering_pct` | int | -100 (gauche) à +100 (droite) |
| `seq` | int | croissant strictement pour une session ; la voiture ignore tout paquet `seq` ≤ dernier accepté |
| `ts_ms` | long | horloge du téléphone, sert uniquement à écarter les paquets trop vieux (> 150 ms) — jamais comparé à l'horloge de la voiture |

`emergency` interrompt ce flux régulier le temps d'un paquet prioritaire,
sans attendre le prochain tick de 20 Hz.

`mode` (`"AUTO"` ou `"MANUAL"`) demande une bascule de mode de conduite
(docs/mobile-app.md, §3 — modèle d'états IDLE → AUTO/MANUAL, toujours sous
supervision d'une session pilote active). Une demande, pas une garantie :
c'est le champ `mode` de la télémétrie qui dit ce que la voiture applique
réellement, même principe que `speed_pct`/`steering_pct` ci-dessous. Envoyé
une fois au clic, pas en continu à 20 Hz comme `drive`.

**Règle de sécurité (NFR du sujet) :** la voiture s'arrête si elle ne reçoit
plus aucun paquet valide (drive/emergency/heartbeat) pendant plus de
**2000 ms**. Ce n'est pas à l'app de le garantir — c'est une règle
côté voiture, comme les cinq règles de sécurité déjà en place côté
Raspberry Pi (`docs/mobile-app.md`, §5).

### Télémétrie — TCP, voiture → app

Flux de lignes JSON, au moins 5 fois par seconde.

```json
{"type":"telemetry","seq":812,"ts_ms":1699999999100,"speed_pct":40,"steering_pct":-15,"battery_pct":76,"rssi_dbm":-58,"mode":"MANUAL"}
```

| Champ | Type | Règle |
|---|---|---|
| `speed_pct`, `steering_pct` | int | ce que la voiture applique réellement, pas ce que l'app a demandé (même principe que `CommandSnapshot` dans `docs/mobile-app.md`) |
| `battery_pct` | int \| null | `null` si non mesurable, jamais `0` ; l'app affiche une alerte sous 20 % |
| `rssi_dbm` | int \| null | force du signal Wi-Fi côté voiture |
| `mode` | `"AUTO"` \| `"MANUAL"` \| null | mode réellement actif ; `null` accepté pour un firmware qui ne le rapporte pas encore, l'app garde alors la dernière valeur demandée côté app |

Côté app, l'absence de trame télémétrie pendant plus de 2000 ms doit être
traitée comme une perte de liaison (bannière d'état + tentative de
reconnexion automatique, voir §Phase 2 de `SmartRCCar_Analyse_TODO_Mobile.pdf`) —
indépendamment de ce que fait la voiture de son côté.

---

## Flux vidéo — relais MJPEG brut, HTTP, voiture → app

**Décision tranchée** (docs/architecture.md, §Décisions bloquantes) : pas de
WebRTC, pas de réencodage GStreamer côté Raspberry Pi. Raison matérielle,
pas de préférence d'équipe — le **Pi 5 n'a pas d'encodeur H.264 matériel**
(retiré par rapport au Pi 4), et la seule caméra du véhicule est
l'**ESP32-CAM**, qui ne parle que MJPEG (`vehicle/esp32-cam/README.md`) et
n'a de toute façon pas la puissance pour autre chose. Le chemin le plus
simple et le plus rapide à mettre en œuvre pour un premier prototype qui
fonctionne : le Raspberry Pi **reproxifie tel quel** le flux
`multipart/x-mixed-replace` de l'ESP32-CAM, octet pour octet, sans décoder
ni réencoder une seule image.

Le téléphone ne se connecte jamais directement à l'ESP32-CAM : il ne connaît
même pas son adresse, seulement `ip:video_port` reçu à la Phase 1. Même
raison que pour le contrôle (§ci-dessus) — un seul point d'entrée réseau
vers la voiture, gardé par le jeton de session.

### `GET /stream` — HTTP, voiture → app

```
GET http://{ip}:{video_port}/stream?token=3f7a1c2e-...
```

Réponse `multipart/x-mixed-replace;boundary=frame`, une partie JPEG par
frame — même format binaire que celui déjà consommé par la vision
(`vehicle/raspberry-pi/src/smart_car/vision/mjpeg_source.py`) : séparateur
`--frame`, en-têtes `Content-Type`/`Content-Length`, `\r\n\r\n`, payload
JPEG, on recommence. Le Raspberry Pi ne fait que dupliquer ce flux vers
chaque client connecté (lui-même pour la vision, et l'app) ; il ne le
réinterprète pas.

`token` en requête, pas dans un en-tête personnalisé : c'est un simple GET
HTTP, il n'y a pas d'autre canal pour prouver la session côté Raspberry Pi.
Le Pi doit rejeter (`403`) un jeton absent, inconnu ou expiré, même règle
que pour les canaux UDP/TCP.

Ce trajet Pi → téléphone est indépendant du contrôle et de la télémétrie :
une coupure vidéo ne doit pas déclencher l'arrêt d'urgence (c'est le silence
sur le canal de contrôle qui le fait, cf. §Commandes ci-dessus), et
inversement l'app doit pouvoir retenter la connexion vidéo seule sans
rouvrir toute la session P2P.

---

## Ce qui n'est pas dans ce document (hors périmètre mobile)

- **Implémentation du Gateway et du côté voiture** : ce contrat leur est
  destiné, mais aucun des deux n'existe encore dans ce dépôt — y compris le
  relais vidéo `GET /stream` décrit ci-dessus, qui suppose une couche
  décision/API Raspberry Pi qui reste à écrire. L'app mobile ne peut donc
  pas être testée en conditions P2P réelles tant que l'un des deux n'a pas
  au moins un mode simulé (sur le modèle de `smart-car-server --simulate`
  côté Raspberry Pi).
