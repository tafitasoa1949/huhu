# Firmware du contrôleur moteur — Personne 3

L'ESP32 reçoit des commandes de conduite du Raspberry Pi sur le port série,
les applique aux moteurs, et coupe tout seul si quelque chose ne va pas.

**Le matériel n'est pas encore monté.** Le firmware est donc écrit pour
compiler et tourner sur une carte ESP32 nue, sans moteur ni capteur branché :
aucun périphérique n'est activé par défaut, la logique de conduite est testée
sur PC, et tout ce qui dépend du câblage réel est regroupé dans un seul
fichier de configuration.

## Démarrage rapide

```bash
pio test -e native      # 44 tests de logique, sur PC, sans carte
pio run                 # compile le firmware
pio run -t upload       # téléverse sur la carte
pio device monitor      # ouvre le moniteur série à 115 200 bauds
```

## Ce que fait le firmware

```
port série  ->  communication  ->  safety  ->  steering  ->  motors  ->  L298N
   JSON         validation        arbitrage    mélange      PWM +
                                  sécurité   différentiel   sens
```

| Fichier | Rôle | Testable sur PC |
|---|---|---|
| `src/communication.cpp` | décodage `DRIVE`, encodage `TELEMETRY` | oui |
| `src/steering_controller.cpp` | `(speed_pct, steering_pct)` → consignes gauche/droite | oui |
| `src/safety.cpp` | watchdog, urgence, bouton, obstacle local | oui |
| `src/motor_controller.cpp` | PWM et sens sur le L298N | non — dépend des broches |
| `src/sensors.cpp` | bouton, ultrasons, encodeurs, batterie | non — dépend des broches |
| `src/main.cpp` | boucle de contrôle | non |

Le découpage n'est pas cosmétique : tout ce qui décide *quoi faire* est du
calcul pur, sans `Arduino.h`, et donc vérifiable sur PC. Il ne reste dans la
partie non testable que le fait d'écrire une valeur sur une broche.

## Direction différentielle

Le châssis n'a pas de servo. Il tourne en faisant varier la vitesse relative
des deux côtés :

```
gauche = vitesse + direction
droite = vitesse - direction
```

Un `steering_pct` négatif ralentit donc le côté gauche et accélère le droit,
ce qui fait tourner à gauche, conformément au contrat.

Deux choix méritent d'être connus :

- **Remise à l'échelle plutôt qu'écrêtage.** Si le mélange sort de
  [-100, 100], les deux côtés sont réduits proportionnellement. Écrêter
  fausserait le rapport entre les roues, donc le rayon de braquage demandé.
- **Vitesse nulle = voiture immobile.** Une commande `speed_pct = 0` avec une
  direction non nulle ne fait pas pivoter la voiture sur place. Le moteur de
  décision n'émet jamais cette combinaison, et « vitesse 0 » doit vouloir dire
  ce qu'il dit. Le pivot reste disponible via `allow_pivot` dans
  `MixerConfig`, désactivé par défaut.

## Câblage prévu (L298N)

| Signal L298N | Broche ESP32 | Rôle |
|---|---|---|
| ENA | 25 | PWM moteur gauche |
| IN1 | 26 | sens moteur gauche |
| IN2 | 27 | sens moteur gauche |
| ENB | 33 | PWM moteur droit |
| IN3 | 32 | sens moteur droit |
| IN4 | 14 | sens moteur droit |

Les broches de strapping (0, 2, 5, 12, 15) sont évitées : un niveau imposé sur
l'une d'elles au moment du reset empêche la carte de démarrer.

**La masse de l'ESP32 et celle du L298N doivent être reliées.** Sans masse
commune, les signaux de commande n'ont pas de référence et le comportement est
imprévisible.

Ne pas alimenter les moteurs depuis le régulateur 5 V de l'ESP32 : ils tirent
bien plus que ce qu'il peut fournir, et les appels de courant font redémarrer
la carte.

## Calibration, une fois le châssis monté

**Ne pas commencer par éditer ce fichier.** Le protocole règle la carte à
chaud, ce qui évite un cycle éditer / compiler / téléverser par essai :

```bash
cd ../raspberry-pi
smart-car-calibrate --port /dev/ttyUSB0
```

L'assistant trouve les valeurs, les enregistre dans `config/calibration.json`
et affiche le bloc à recopier ici. Procédure complète dans
`docs/calibration.md`.

`pin_config.h` reste les **valeurs par défaut appliquées à la mise sous
tension**, avant que le Raspberry Pi ait parlé — c'est ce qui rend la voiture
sûre entre le branchement et la première connexion. On y recopie le profil une
fois qu'il est stable.

Ce que l'assistant cherche, dans cet ordre :

1. **Sens de rotation.** Roues levées, envoyer `speed_pct = 30`,
   `steering_pct = 0`. Les deux roues doivent tourner vers l'avant. Pour celle
   qui tourne à l'envers, passer `MOTOR_LEFT_INVERT` ou `MOTOR_RIGHT_INVERT`
   à `1` — c'est plus sûr que de recâbler, et ça se relit.
2. **Sens de la direction.** Envoyer `steering_pct = -40` et vérifier que la
   voiture tourne bien **à gauche**. Une inversion ici met tout le pipeline en
   contre-réaction positive : la voiture s'écarte de la piste au lieu d'y
   revenir.
3. **Seuil de démarrage.** Au sol, augmenter `speed_pct` par pas de 5 jusqu'à
   ce que les roues tournent réellement. Reporter cette valeur dans
   `MOTOR_MIN_DUTY_PCT` : les consignes non nulles seront remises à l'échelle
   au-dessus de ce seuil, au lieu de faire chauffer les moteurs sans les faire
   tourner.
4. **Plafond de vitesse.** `MOTOR_MAX_DUTY_PCT` est à **40** pour les premiers
   essais, ce qui laisse le temps de rattraper la voiture à la main. À
   remonter progressivement, pas d'emblée.
5. **Autorité de la direction.** Si la voiture braque trop sec, baisser
   `STEERING_GAIN_PCT` — cela n'oblige pas à retoucher le moteur de décision.

## Capteurs optionnels

Tous désactivés par défaut. Passer le `ENABLE_*` correspondant à `1` dans
`include/pin_config.h` quand le composant est branché.

| Bloc | Broches par défaut | Remonté dans la télémétrie |
|---|---|---|
| `ENABLE_EMERGENCY_BUTTON` | 13 (`INPUT_PULLUP`, actif bas) | non, agit sur la sécurité |
| `ENABLE_ULTRASONIC` | TRIG 4, ECHO 36 | `obstacle_distance_m` |
| `ENABLE_ENCODERS` | 18, 19 | `left_rpm`, `right_rpm` |
| `ENABLE_BATTERY_MONITOR` | ADC 39 | `battery_pct` |

⚠️ La sortie ECHO du HC-SR04 est en 5 V. Un pont diviseur vers 3,3 V est
nécessaire, sinon la broche de l'ESP32 est endommagée.

Un bloc désactivé renvoie « valeur inconnue », sérialisée en `null`. La
télémétrie reste conforme au contrat sur une carte nue.

## Sécurité

Voir `docs/communication-protocol.md`, section 5, pour l'ordre de priorité
complet. En résumé : le bouton physique prime sur tout, puis l'urgence
logicielle, puis l'obstacle local, puis les erreurs de protocole, puis le
watchdog de 500 ms.

Avant les premiers essais moteurs (annexe D du plan) :

- essais **roues levées** d'abord, puis au sol à très faible vitesse ;
- zone fermée et dégagée, pas d'escalier, pas d'enfants, pas d'animaux ;
- bouton d'arrêt d'urgence physique branché et testé ;
- coupure d'alimentation accessible à la main ;
- sens de rotation de chaque moteur vérifié séparément ;
- `MOTOR_MAX_DUTY_PCT` laissé bas.

## Notes de compilation

- **ArduinoJson est figé en version 6.** `StaticJsonDocument` alloue sur la
  pile ; le `JsonDocument` de la version 7 passe par le tas, ce qu'on évite
  dans une boucle qui tourne en continu.
- **L'API LEDC diffère entre les cœurs Arduino-ESP32 2.x et 3.x.** Le firmware
  détecte la version et s'adapte, personne n'a besoin de figer la sienne.
- **Les durées sont en `uint32_t`, pas en `unsigned long`.** C'est la largeur
  de `millis()` sur l'ESP32 ; sur un PC, `unsigned long` fait 64 bits et le
  débordement du compteur ne se comporterait pas pareil dans les tests.
