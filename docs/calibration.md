# Calibration du châssis — le jour du montage

Ce document décrit ce qu'il faut faire quand la voiture arrive, et pourquoi la
calibration ne peut pas être faite d'avance.

## Ce qui ne peut pas être deviné

Trois choses dépendent du matériel réel et d'aucun code :

1. **La polarité du câblage.** Le sens dans lequel un moteur tourne dépend de
   l'ordre des deux fils sur le bornier. Il y a une chance sur deux par
   moteur.
2. **Le seuil de démarrage.** En dessous d'un certain rapport cyclique, un
   moteur à courant continu chargé ne tourne pas : il chauffe. La valeur
   dépend des moteurs, de la masse du châssis et de la batterie.
3. **Le sens mécanique de la direction.** Sur un châssis différentiel, il
   découle des deux premiers, mais un moteur branché sur le mauvais canal du
   driver inverserait tout.

Aucun de ces points n'est devinable. Ce qui a été fait, c'est que les
**découvrir prenne quelques minutes**, sans recompiler ni téléverser une seule
fois.

## Pourquoi pas simplement `pin_config.h`

Modifier `pin_config.h` impose un cycle éditer → compiler → téléverser →
tester, soit une à deux minutes par essai. Sur une quinzaine d'essais, c'est
une demi-journée.

Le protocole porte donc deux messages, `CONFIG` et `TEST`, qui règlent la
carte **à chaud**. La boucle passe de deux minutes à deux secondes.

`pin_config.h` garde son rôle : ce sont les **valeurs par défaut appliquées à
la mise sous tension**, avant que le Raspberry Pi ait dit quoi que ce soit.
C'est ce qui rend la voiture sûre entre le branchement et la première
connexion. Une fois la calibration stabilisée, on y recopie le bloc généré.

## Où vit le profil

```
vehicle/raspberry-pi/config/calibration.json   ← source de vérité, versionnée dans git
        │
        │  renvoyé à chaque connexion et à chaque entrée en calibration
        ▼
    ESP32 (en RAM)
        ▲
        │  valeurs de repli au démarrage
pin_config.h
```

Rien n'est écrit dans la mémoire flash de la carte : **remplacer un ESP32 ne
perd aucun réglage**, et il n'y a jamais deux versions du profil à réconcilier.

## Procédure

### Option 1 — l'assistant en ligne de commande

C'est la voie recommandée tant que l'application mobile n'existe pas.

Après `pip install -e .` dans `vehicle/raspberry-pi/`, la commande est disponible
depuis n'importe quel dossier, sans réglage de `PYTHONPATH` :

```bash
smart-car-calibrate --port /dev/ttyUSB0      # Linux, Raspberry Pi
smart-car-calibrate --port COM3              # Windows
```

Répétition à blanc, sans rien brancher, pour se familiariser :

```bash
smart-car-calibrate --simulate
```

L'assistant déroule :

1. **confirmation que les roues sont levées** — il refuse de démarrer sinon ;
2. **sens du moteur gauche** — la roue tourne 2 s, on répond o/n, l'inversion
   est activée et l'essai relancé jusqu'à ce que ce soit bon ;
3. **sens du moteur droit** — pareil ;
4. **seuil de démarrage** — au sol, essais par pas de 5 % jusqu'à ce que les
   roues tournent vraiment ;
5. **sens de la direction** — une vraie commande de conduite à gauche, à
   vérifier des yeux ;
6. **plafond de vitesse** pour les prochains essais ;
7. **enregistrement**, puis affichage du bloc à recopier dans `pin_config.h`.

### Option 2 — l'API

Les mêmes étapes sont exposées pour l'application mobile :

| Méthode | Endpoint | Rôle |
|---|---|---|
| `GET` | `/api/calibration` | profil, confirmation de l'ESP32, bloc `pin_config` |
| `POST` | `/api/calibration` | modifier un ou plusieurs réglages |
| `GET` | `/api/calibration/steps` | la procédure guidée, dans l'ordre |
| `POST` | `/api/calibration/test` | faire tourner une roue |
| `POST` | `/api/calibration/stop` | arrêter — sans autorisation |
| `POST` | `/api/calibration/save` | figer le profil sur disque |

Un essai moteur exige le mode `CALIBRATION`, qui exige lui-même d'être en
`IDLE` : on ne bascule pas en calibration depuis la conduite.

`GET /api/calibration/steps` sert à ce que l'application et l'assistant en
ligne de commande racontent exactement la même procédure.

## Sécurité pendant la calibration

- **Roues levées** pour les étapes 2 et 3. L'assistant le demande et refuse de
  continuer sinon.
- **Le watchdog de 500 ms reste souverain**, sans exception. Un essai « long »
  est un train d'impulsions courtes, pas une commande longue.
- **Les essais sont bornés** côté firmware : ±60 % de rapport cyclique,
  3 000 ms maximum. Impossible de détourner l'outil en pilotage.
- **Arrêter ne demande aucune autorisation** — ni `/api/calibration/stop`, ni
  l'arrêt d'urgence.
- **Une roue ne reste jamais en rotation** : l'assistant coupe même en cas
  d'interruption clavier.

## Après la calibration

1. Vérifier que `config/calibration.json` est bien versionné.
2. Recopier le bloc affiché dans `vehicle/esp32-controller/include/pin_config.h` :

   ```c
   #define MOTOR_LEFT_INVERT 1
   #define MOTOR_RIGHT_INVERT 0
   #define MOTOR_MIN_DUTY_PCT 18
   #define MOTOR_MAX_DUTY_PCT 40
   #define STEERING_GAIN_PCT 100
   ```

3. Recompiler une dernière fois, pour que ces valeurs s'appliquent dès la mise
   sous tension.
4. Remonter `MOTOR_MAX_DUTY_PCT` progressivement, pas d'emblée.

## Limite connue

Si l'ESP32 redémarre en cours de session — coupure d'alimentation, reset — il
repart sur les valeurs de `pin_config.h` et le serveur ne le détecte pas
automatiquement. Repasser en mode `CALIBRATION` une fois, ou redémarrer le
serveur, renvoie le profil. C'est aussi la raison pour laquelle il faut
recopier le profil dans `pin_config.h` une fois qu'il est stable.
