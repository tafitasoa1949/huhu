# Caméra de conduite (ESP32-CAM) — Personne 3

Module AI-Thinker ESP32-CAM. C'est **la seule caméra du véhicule** : le
Raspberry Pi n'a pas de capteur CSI/USB qui lui soit propre. La carte rejoint
le Wi-Fi local et sert un flux MJPEG en HTTP.

**Un seul client s'y connecte directement : le Raspberry Pi**, qui lit
`/stream` pour deux usages à la fois — voir `docs/architecture.md`,
§Décisions tranchées, et `docs/mobile-protocol.md`, §Flux vidéo :

- la **vision** (Personne 1), qui produit `PerceptionResult` (détection de
  piste) à partir de ces mêmes frames ;
- le **relais vers l'application mobile** : le Pi reproxifie le flux tel
  quel (octet pour octet, sans réencodage — le Pi 5 n'a pas d'encodeur H.264
  matériel) sur son propre port `video_port` (Phase 2, P2P). **Le téléphone
  ne se connecte jamais directement à l'ESP32-CAM** — il ne connaît même pas
  son adresse, seulement celle du Raspberry Pi reçue du Gateway à la
  Phase 1. Même raison que pour le contrôle : un seul point d'entrée réseau
  vers la voiture, gardé par le jeton de session.

Cette carte ne parle jamais à l'ESP32 de contrôle : le lien avec le pilotage
passe uniquement par le Raspberry Pi, qui transforme les frames en
`PerceptionResult` puis en `DriveCommand`.

## Démarrage rapide

1. Copier `include/wifi_secrets.example.h` en `include/wifi_secrets.h` (ce
   dernier n'est pas versionné) et y renseigner le SSID et le mot de passe du
   réseau de démonstration — le même que celui utilisé par le Raspberry Pi et
   le téléphone. Ne jamais mettre de vrais identifiants dans
   `cam_config.h` : c'est justement pour ça que `wifi_secrets.h` en a été
   sorti.
2. Brancher la carte en programmation (GPIO 0 à la masse au reset, comme
   tout ESP32-CAM — pas d'adaptateur USB intégré sur ce module).

```bash
pio run                 # compile le firmware
pio run -t upload       # téléverse (GPIO 0 à la masse pendant le reset)
pio device monitor      # moniteur série à 115200 bauds — affiche l'IP obtenue
```

Après démarrage, le flux est disponible sur `http://<ip-de-la-carte>:81/stream`.
La LED intégrée clignote trois fois quand le serveur est prêt à répondre, puis
s'éteint : c'est le flash de la carte, le laisser allumé chaufferait et
éblouirait la scène filmée.

`http://<ip-de-la-carte>:81/snapshot` renvoie une seule image JPEG, hors du
flux continu — pratique pour vérifier que la caméra voit quelque chose
(`curl -o test.jpg ...`, ou directement dans un navigateur) sans avoir à
décoder du multipart pour une simple sonde.

`http://<ip-de-la-carte>:81/status` renvoie un JSON de télémétrie de la
carte — pas de la voiture :

```json
{"uptime_ms":128340,"rssi_dbm":-58,"free_heap_bytes":142016,"fps":24.3,"frame_width":320,"frame_height":240,"jpeg_quality":12}
```

`fps` est un débit *livré*, lissé, mesuré sur les frames effectivement
envoyées à `/stream` — il reste à 0 tant qu'aucun client ne s'est connecté.
`frame_width`/`frame_height` reflètent la résolution réellement active,
utile pour repérer un repli QQVGA (PSRAM absente) sans relire le port série.

Si la PSRAM n'est pas détectée, le firmware ne s'arrête pas : il retombe en
QQVGA sur un seul tampon et le signale sur le port série.

## Pourquoi ce n'est pas testé sur PC

Contrairement à `esp32-controller`, il n'y a pas de découpage "logique pure
testable / broches non testables" ici : le rôle de ce firmware — capturer,
encoder en JPEG, servir en HTTP — dépend en totalité de la puce caméra et de
la pile Wi-Fi, aucune des deux n'étant simulable de façon utile sur PC. La
partie qui bénéficierait le plus de tests (le multiplexage MJPEG) est une
vingtaine de lignes directement issues de l'API `esp_http_server`.

## Ce qui reste à câbler/ajuster une fois la carte en main

- Vérifier `CAM_FRAME_SIZE` / `CAM_JPEG_QUALITY` dans `cam_config.h` une fois
  la latence réelle mesurée sur le réseau de démonstration : la résolution
  QVGA (320×240) est un point de départ prudent, pas une valeur figée.
- `STREAM_SERVER_PORT` (81 par défaut) doit rester différent du port de
  l'API du Raspberry Pi si les deux finissent sur la même adresse (ce n'est
  pas le cas actuellement : deux cartes, deux adresses IP).
- Ne pas alimenter la carte depuis le même régulateur 5 V que les moteurs de
  `esp32-controller` — même remarque que dans `esp32-controller/README.md` :
  les appels de courant du moteur peuvent faire redémarrer une carte Wi-Fi
  sensible aux chutes de tension pendant la capture.
