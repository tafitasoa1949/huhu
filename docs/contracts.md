# Contrats communs

Référence : section 4 du plan de développement. Ces structures sont définies
une seule fois, dans `vehicle/raspberry-pi/src/smart_car/shared/models.py`. Vision,
décision et contrôle doivent les importer plutôt que redéclarer les leurs.

> **Changement de contrat — à valider par les trois personnes.**
> Cette page a été alignée sur la section 4 du plan. Les noms de champs ont
> changé par rapport à la première version du dépôt :
> `error` → `error_px`, `speed` → `speed_pct`, `steering` → `steering_pct`,
> et `DriveCommand` porte désormais `sequence` et `emergency`. Les champs
> `road_center_x`, `image_center_x`, `ObstacleResult`, `PerceptionResult` et
> `Telemetry` ont été ajoutés. L'énumération `CarAction` est remplacée par le
> type `Action` du plan.

## Conventions

| Élément | Convention |
|---|---|
| Vitesse | `speed_pct`, entier de 0 à 100, jamais négatif |
| Direction | `steering_pct`, entier de -100 à +100 |
| Gauche | valeur **négative** |
| Droite | valeur **positive** |
| Tout droit | 0 |
| Distance | mètres, suffixe `_m` |
| Erreur de piste | pixels, suffixe `_px` |
| Temps | millisecondes monotoniques, suffixe `_ms` |
| Confiance | flottant de 0.0 à 1.0 |
| Valeur inconnue | `None` / `null` — jamais 0 |

La dernière ligne est la source de la moitié des bugs d'intégration : une
distance à `None` veut dire « je ne sais pas », pas « rien devant ».

## `LaneResult` — produit par la vision

| Champ | Type | Règle |
|---|---|---|
| `detected` | bool | vrai uniquement si la piste est suffisamment fiable |
| `error_px` | float | `road_center_x - image_center_x`, négatif = piste à gauche |
| `confidence` | float | 0.0 à 1.0, seuil MVP 0.55 |
| `road_center_x` | int \| None | centre estimé de la piste, `None` si perdue |
| `image_center_x` | int | largeur de l'image divisée par deux |

## `ObstacleResult` — produit par la vision

| Champ | Type | Règle |
|---|---|---|
| `detected` | bool | vrai si un obstacle est considéré présent |
| `distance_m` | float \| None | distance en mètres, `None` si inconnue |
| `confidence` | float | 0.0 à 1.0 |
| `source` | str | `camera`, `ultrasonic`, `simulation`… |

## `PerceptionResult` — vision vers décision

| Champ | Type |
|---|---|
| `frame_id` | int |
| `lane` | `LaneResult` |
| `obstacle` | `ObstacleResult` |

## `DriveCommand` — décision vers contrôle

| Champ | Type | Règle |
|---|---|---|
| `sequence` | int | compteur croissant, apparie commande et télémétrie |
| `action` | `Action` | `FORWARD`, `TURN_LEFT`, `TURN_RIGHT`, `STOP`, `EMERGENCY_STOP` |
| `speed_pct` | int | 0 à 100 |
| `steering_pct` | int | -100 à +100 |
| `emergency` | bool | vrai impose un arrêt immédiat |

Les bornes ne sont **pas** vérifiées à la construction : les tests du protocole
doivent pouvoir fabriquer des commandes hors plage pour vérifier qu'elles sont
bien rejetées (scénario S10). La validation se fait par `validate_command()`,
appelée systématiquement par les contrôleurs avant tout envoi.

## `Telemetry` — ESP32 vers Raspberry Pi

| Champ | Type |
|---|---|
| `sequence` | int |
| `status` | str (`OK` ou `ERROR`) |
| `obstacle_distance_m` | float \| None |
| `battery_pct` | int \| None |
| `left_rpm`, `right_rpm` | float \| None |
| `error` | str \| None |

## Validation

`validate_command()` refuse une commande si :

- l'action n'est pas l'une des cinq valeurs du contrat ;
- `speed_pct` sort de [0, 100] ;
- `steering_pct` sort de [-100, 100] ;
- `emergency` est vrai alors que `speed_pct` n'est pas nul ;
- `sequence` est négatif.

## Exemples officiels

Piste centrée, aucun obstacle :

```json
{
  "frame_id": 100,
  "lane": {"detected": true, "error_px": 8.0, "confidence": 0.92,
           "road_center_x": 328, "image_center_x": 320},
  "obstacle": {"detected": false, "distance_m": null,
               "confidence": 0.0, "source": "camera"}
}
```

donne :

```json
{"sequence": 100, "action": "FORWARD", "speed_pct": 45,
 "steering_pct": 0, "emergency": false}
```

Voir `docs/communication-protocol.md` pour la traduction de cette commande en
trame série.
