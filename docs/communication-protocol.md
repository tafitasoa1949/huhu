# Protocole Raspberry Pi ↔ ESP32

Ticket ESP-01. Ce document est la référence du dialogue série entre le
Raspberry Pi 5 (qui décide) et l'ESP32 (qui pilote les moteurs). Il reprend la
section 5 du plan de développement et précise ce que le firmware fait
réellement.

Les deux implémentations sont testées l'une contre l'autre :

- côté Python : `vehicle/raspberry-pi/tests/test_protocol.py`
- côté ESP32 : `vehicle/esp32-controller/test/test_protocol/`

Si l'un des deux jeux de tests change, l'autre doit changer aussi.

## 1. Liaison

| Paramètre | Valeur |
|---|---|
| Transport | USB série |
| Port Linux | `/dev/ttyUSB0` ou `/dev/ttyACM0` |
| Vitesse | 115 200 bauds |
| Format | 8 bits, sans parité, 1 bit d'arrêt |
| Délai de lecture | 0,1 s côté Raspberry Pi |
| Encodage | UTF-8 |
| Trame | un objet JSON compact par ligne, terminé par `\n` |

Le JSON est compact, sans espace : le tampon de ligne du firmware est borné à
192 octets (`protocol::MAX_LINE_LENGTH`). Une ligne plus longue est consommée
jusqu'au saut de ligne pour se resynchroniser, puis signalée en erreur
`LINE_TOO_LONG`.

## 2. Message `DRIVE` — Raspberry Pi vers ESP32

```json
{"type":"DRIVE","sequence":18,"speed_pct":35,"steering_pct":-25,"emergency":false}
```

| Champ | Type | Obligatoire | Règle |
|---|---|---|---|
| `type` | string | oui | toujours `DRIVE` |
| `sequence` | int | oui | croissant, sert à apparier la réponse |
| `speed_pct` | int | oui | 0 à 100, jamais négatif |
| `steering_pct` | int | oui | -100 à +100, négatif = gauche |
| `emergency` | bool | oui | si `true`, la vitesse est ignorée et la voiture s'arrête |

L'ordre des clés fait partie du contrat : les tests comparent la ligne octet
pour octet.

L'action symbolique (`FORWARD`, `TURN_LEFT`…) n'est **pas** transmise. C'est un
concept du moteur de décision ; le firmware n'applique que la vitesse et la
direction. La transmettre créerait deux sources de vérité pour un même
comportement.

## 3. Message `TELEMETRY` — ESP32 vers Raspberry Pi

```json
{"type":"TELEMETRY","sequence":18,"status":"OK","obstacle_distance_m":1.42,"battery_pct":82,"left_rpm":118.00,"right_rpm":120.00,"error":null}
```

| Champ | Type | Règle |
|---|---|---|
| `type` | string | toujours `TELEMETRY` |
| `sequence` | int | séquence de la dernière commande valide reçue |
| `status` | string | `OK` ou `ERROR` |
| `obstacle_distance_m` | float \| null | `null` si le capteur est absent ou hors de portée |
| `battery_pct` | int \| null | `null` si la mesure de tension n'est pas câblée |
| `left_rpm`, `right_rpm` | float \| null | `null` si les encodeurs ne sont pas câblés |
| `error` | string \| null | code d'erreur si `status` vaut `ERROR` |

**`null` veut dire « inconnu », jamais « zéro ».** Une carte ESP32 nue, sans
aucun périphérique branché, renvoie une télémétrie parfaitement valide dont
tous les champs mesurés valent `null`. C'est ce qui permet de tester le
protocole complet avant que les capteurs existent.

### Quand la télémétrie est émise

- en réponse à chaque ligne reçue, valide ou non ;
- toutes les 250 ms en l'absence de commande.

Le battement périodique existe pour que le Raspberry Pi puisse distinguer
« l'ESP32 est passé en `COMMAND_TIMEOUT` » de « le câble est débranché ». Sans
lui, les deux se présenteraient comme un simple silence.

## 4. Codes d'erreur

| Code | Cause |
|---|---|
| `INVALID_JSON` | ligne vide ou JSON malformé |
| `UNKNOWN_TYPE` | champ `type` différent de `DRIVE` |
| `MISSING_FIELD` | un champ obligatoire est absent ou n'a pas le bon type |
| `INVALID_SPEED` | `speed_pct` hors de [0, 100] |
| `INVALID_STEERING` | `steering_pct` hors de [-100, 100] |
| `LINE_TOO_LONG` | ligne dépassant 192 octets |
| `COMMAND_TIMEOUT` | plus de 500 ms sans commande valide |
| `EMERGENCY_STOP` | arrêt d'urgence demandé, ou bouton physique enfoncé |
| `LOCAL_OBSTACLE` | le télémètre de l'ESP32 voit un obstacle critique |
| `INVALID_CONFIG` | réglage de calibration hors de [0, 100] ou mal typé |
| `INVALID_TARGET` | cible d'essai moteur différente de LEFT, RIGHT ou BOTH |
| `INVALID_DUTY` | rapport cyclique d'essai au-delà de ±60 % |
| `INVALID_DURATION` | durée d'essai nulle ou supérieure à 3 000 ms |

## 5. Sécurité

L'ESP32 coupe les moteurs de sa propre initiative dans les cas suivants,
évalués dans cet ordre de priorité :

1. **bouton d'arrêt d'urgence physique** enfoncé ;
2. **`emergency = true`** dans la dernière commande valide ;
3. **obstacle critique** vu par le télémètre local (≤ 0,25 m) ;
4. **dernière ligne rejetée** — la voiture reste immobile jusqu'à réception
   d'une commande valide ; une erreur de protocole ne s'efface pas toute
   seule ;
5. **aucune commande reçue** depuis le démarrage ;
6. **silence de plus de 500 ms** (`COMMAND_TIMEOUT_MS`).

Une cause matérielle prime toujours sur une cause logicielle, et toute cause
de sécurité prime sur la conduite normale.

Les trois premières provoquent un **freinage actif** (les deux bornes du moteur
mises au même potentiel) : en situation d'urgence, la distance d'arrêt prime
sur la douceur mécanique. Les trois dernières laissent la voiture en **roue
libre**.

L'arbitrage est implémenté dans `vehicle/esp32-controller/src/safety.cpp` sous forme de
fonction pure, ce qui permet de le tester exhaustivement sur PC — y compris le
débordement du compteur `millis()`, qui survient tous les 49 jours environ.

## 6. Numéros de séquence

Le numéro de séquence est le seul lien entre les deux sens du dialogue. Le
Raspberry Pi l'incrémente à chaque décision ; l'ESP32 le renvoie tel quel.

La séquence **0** est réservée aux arrêts émis en marge du flux de décision
(fin de programme, interruption clavier). Le firmware ne vérifie pas que la
séquence croît : une commande dont la séquence recule reste appliquée. C'est
volontaire — refuser une commande d'arrêt parce que sa séquence est basse
serait exactement le mauvais comportement.

## 7. Messages de calibration

Deux messages supplémentaires servent à régler le châssis **à chaud**, sans
recompiler ni téléverser. Voir `docs/calibration.md` pour la procédure.

### `CONFIG` — réglage à chaud, dans les deux sens

```json
{"type":"CONFIG","sequence":12,"invert_left":true,"min_duty_pct":18}
```

| Champ | Type | Obligatoire | Règle |
|---|---|---|---|
| `type` | string | oui | `CONFIG` |
| `sequence` | int | oui | croissant |
| `steering_gain_pct` | int | non | 0 à 100 |
| `min_duty_pct` | int | non | 0 à 100 |
| `max_duty_pct` | int | non | 0 à 100 |
| `invert_left` | bool | non | |
| `invert_right` | bool | non | |

**Mise à jour partielle** : la ligne ne modifie que ce qu'elle mentionne. On
corrige ainsi l'inversion d'un moteur sans risquer d'écraser un seuil trouvé
dix secondes plus tôt. Une ligne sans aucun réglage est une demande de
lecture.

L'ESP32 répond par une ligne `CONFIG` contenant la configuration
**effectivement retenue**, après bornage :

```json
{"type":"CONFIG","sequence":12,"steering_gain_pct":100,"min_duty_pct":18,"max_duty_pct":40,"invert_left":true,"invert_right":false}
```

Le Raspberry Pi compare ce qu'il a demandé à ce qui a été retenu, plutôt que
de supposer que sa demande a été suivie.

Un `CONFIG` remet la consigne de conduite à zéro : changer la calibration en
pleine conduite ferait partir la voiture de travers.

### `TEST` — essai moteur

```json
{"type":"TEST","sequence":13,"target":"LEFT","duty_pct":30,"duration_ms":300}
```

| Champ | Type | Règle |
|---|---|---|
| `target` | string | `LEFT`, `RIGHT` ou `BOTH` |
| `duty_pct` | int | -60 à +60, signé |
| `duration_ms` | int | 1 à 3 000 |

Pilote un côté **directement**, sans passer par le mélange différentiel. C'est
indispensable pour vérifier le sens de rotation moteur par moteur, ce qu'une
commande `DRIVE` ne permet pas puisqu'elle agit forcément sur les deux côtés.

Deux règles à connaître :

- **L'essai applique l'inversion** (`invert_left` / `invert_right`) — c'est
  tout l'intérêt de la boucle « je teste, j'inverse, je re-teste ».
- **L'essai n'applique ni le plafond ni le seuil de démarrage.** Chercher à
  quel rapport cyclique une roue commence à tourner n'aurait aucun sens si la
  valeur demandée était elle-même remise à l'échelle.

Une commande `DRIVE` annule un essai en cours. Après expiration, la voiture
est à l'arrêt : elle ne repart pas sur la dernière consigne de conduite reçue.

### Le watchdog n'est jamais suspendu

Un essai qui dure deux secondes n'est **pas** une commande de deux secondes,
mais un train d'impulsions de 300 ms émises toutes les 100 ms. L'opérateur
voit une roue tourner en continu, et l'invariant « plus de commande pendant
500 ms, les moteurs s'arrêtent » reste vrai sans exception. La borne de
3 000 ms du firmware est une sécurité, pas le mécanisme normal.

## 8. Vérification sans matériel

```bash
cd vehicle/raspberry-pi
python3 -m pytest                       # 114 tests côté Python

cd ../esp32-controller
pio test -e native                      # 44 tests de logique côté ESP32

cd ..
python3 tools/check_simulator_parity.py # concordance C++ / ESP32 virtuel
```

### Installation

```bash
cd vehicle/raspberry-pi
python3 -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

L'installation en mode éditable rend `smart-car`, `smart-car-server` et
`smart-car-calibrate` disponibles depuis n'importe quel dossier, sans avoir à
régler `PYTHONPATH`. Ajouter `.[vision]` pour opencv, dont la couche contrôle
n'a pas besoin.

### Les quatre modes d'exécution

```bash
smart-car --mode <mode> [options]
```

| Mode | Ce qu'il y a au bout du câble | Ce qu'il valide |
|---|---|---|
| `simulation` | rien, les commandes sont affichées | la production des commandes |
| `fake` | un port qui enregistre et rejoue | la trame, octet pour octet |
| `virtual` | un **ESP32 virtuel** qui réagit | le comportement complet |
| `hardware` | la vraie carte | l'intégration réelle |

Le mode `virtual` rejoue la logique du firmware — validation, watchdog,
mélange différentiel, arbitrage de sécurité — et affiche ce que feraient les
moteurs :

```
TURN_LEFT       v= 30%  dir= -30%  |  G ░░░░░░░░░░░░   +0%   D ▌▌▌░░░░░░░░░  +24%  |  ACTIVE DRIVING
EMERGENCY_STOP  v=  0%  dir=  +0%  |  G ░░░░░░░░░░░░   +0%   D ░░░░░░░░░░░░   +0%  |  EMERGENCY_COMMAND BRAKE
```

Le watchdog y est observable directement : à une cadence inférieure à 2 Hz, le
silence dépasse les 500 ms autorisées et les moteurs sont coupés.

```bash
smart-car --mode virtual --source pilot --rate-hz 1
```

### Les deux sources de commandes

- `--source scenario --scenario <nom>` : suite figée (`nominal`, `emergency`,
  `lane_lost`, `limits`, `invalid`), utile pour les cas limites ;
- `--source pilot --track <nom>` : flux continu produit par le **pilote
  virtuel** (`curves`, `lane_loss`, `obstacle`).

Le pilote virtuel est un bouchon appartenant à l'outillage de la Personne 3, à
supprimer dès que le moteur de décision de la Personne 2 existe. Il applique
volontairement les règles de la section 7.2 du plan pour produire des
commandes ressemblant à celles qui viendront.

### Sur la double implémentation

L'ESP32 virtuel est une transcription Python du firmware C++, donc une seconde
source de vérité qui peut dériver. `tools/check_simulator_parity.py` compile la
logique C++ et compare les deux sur plus de 1 200 cas — mélange différentiel
sur toute la grille des vitesses, directions et réglages de calibration, et
arbitrage de sécurité y compris au débordement de `millis()`. **À relancer
après toute modification de `steering_controller.cpp` ou `safety.cpp`.** Il ne
demande qu'un compilateur C++, ni PlatformIO ni carte.
