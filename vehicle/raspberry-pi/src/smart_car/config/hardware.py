"""Brochage et calibration matérielle — le seul fichier à corriger le jour
du câblage réel, même rôle que l'ancien `esp32-controller/include/pin_config.h`
(docs/calibration.md : « un seul fichier à corriger, aucun autre ne doit
contenir de numéro de broche »).

Les largeurs d'impulsion sont en **microsecondes**, l'unité dans laquelle un
ESC/servo se raisonne et celle que `lgpio.tx_servo` prend directement (voir
`motors/gpio_driver.py`).
"""

# --------------------------------------------------------------------------
# Brochage GPIO (BCM)
# --------------------------------------------------------------------------
# Deux ESC de propulsion en tandem — pas un ESC + un servo de direction
# comme le supposait la première version de ce fichier. Aucun servo de
# direction n'est câblé pour l'instant (voir STEERING_PIN ci-dessous) :
# c'est un changement de câblage volontaire, pas un oubli.
ESC_PIN = 12  # broche physique 32 (BCM 12) — moteur 1, câblage confirmé
ESC2_PIN = 13  # broche physique 33 (BCM 13) — moteur 2, câblage confirmé

# `None` = pas de servo de direction câblé pour l'instant : `GpioMotorDriver`
# n'essaie alors ni de le revendiquer ni de lui envoyer d'impulsion.
# Remettre un numéro de broche ici (ex. 18) suffira le jour où un servo sera
# câblé — rien d'autre à changer.
STEERING_PIN: int | None = None

# --------------------------------------------------------------------------
# Cadence du signal (standard hobby RC : 50 Hz, une impulsion toutes les 20 ms)
# --------------------------------------------------------------------------
PWM_FREQUENCY_HZ = 50

# --------------------------------------------------------------------------
# Plage utile de l'ESC — mesurée au banc sur le moteur 1, PAS la plage hobby
# générique
# --------------------------------------------------------------------------
# Le standard hobby est 1000-2000 µs, mais cet ESC-ci ne répond que dans le
# premier cinquième de cette plage : essai manuel au banc (rapport cyclique à
# 50 Hz) — 0.06 = 1200 µs = plein régime avant. Au-delà, le moteur bourdonne
# sans tourner : le signal est hors de ce que cet ESC sait interpréter.
#
# Le point bas n'est PAS 1000 µs comme le suggérerait le standard hobby :
# balayage au banc (900/950/980/1000/1020/1050/1100 µs, 4 s chacun), seul
# 900 µs est resté parfaitement stable. À 1000 µs, le moteur vibrait —
# 1000 µs est exactement le seuil que cet ESC interprète comme « commence à
# avancer », et le signal logiciel (PWMOutputDevice/lgpio, pas le vrai PWM
# matériel du Pi 5) déborde par endroits au-dessus par jitter de minutage,
# suffisant pour déclencher ce seuil de façon intermittente. 900 µs laisse
# une marge de sécurité sous ce seuil plutôt que de s'y coller.
#
# **Le moteur 2 (ESC2_PIN) réutilise cette même plage, non revérifiée sur
# lui** : deux ESC, même modèle apparent, ne partagent pas forcément le même
# seuil de démarrage ni le même neutre stable. À confirmer au banc pour le
# moteur 2 avant de lui faire confiance à pleine puissance (même procédure
# que pour le moteur 1 : balayage neutre, puis armement + balayage de
# vérification 0/25/50/75/100 %).
ESC_MIN_PULSE_US = 900  # arrêt / neutre d'armement — marge sous le seuil réel de l'ESC
ESC_MAX_PULSE_US = 1200  # plein régime avant

# Le servo de direction, lui, serait un servo hobby ordinaire : plage
# complète, centré au milieu. Rien à voir avec la plage étroite de l'ESC
# ci-dessus. Conservé pour le jour où STEERING_PIN sera à nouveau câblé —
# ignoré tant qu'il vaut None.
STEERING_MIN_PULSE_US = 1000  # butée gauche
STEERING_MAX_PULSE_US = 2000  # butée droite

# --------------------------------------------------------------------------
# Sens de rotation / de braquage
# --------------------------------------------------------------------------
# À valider roues levées avant tout essai au sol, comme pour l'ancien
# châssis différentiel (docs/calibration.md). Si le sens réel est inversé,
# basculer la valeur ici plutôt que d'inverser les fils du signal.
#
# Un seul réglage pour les deux moteurs de propulsion : ils tournent en
# tandem sur la même commande de vitesse (voir `motors/gpio_driver.py`), pas
# de mélange différentiel gauche/droite indépendant ici.
ESC_INVERT = False
STEERING_INVERT = False

# --------------------------------------------------------------------------
# Type d'ESC — change ce que "vitesse nulle" veut dire sur le fil
# --------------------------------------------------------------------------
# Deux conventions incompatibles partagent le même signal :
#
# - bidirectionnel (True)  : impulsion minimale = pleine marche arrière,
#   milieu = arrêt/neutre, maximale = plein avant. C'est ce que suppose
#   `docs/mobile-protocol.md` pour `speed_pct` ∈ [-100, 100].
# - unidirectionnel (False) : impulsion minimale = arrêt, maximale = plein
#   régime avant, rien en dessous du minimum (pas de marche arrière). C'est
#   le moteur câblé ici, confirmé au banc.
#
# `GpioMotorDriver` arme et arrête les deux ESC au bon neutre selon cette
# valeur, et un `speed_pct` négatif est ramené à l'arrêt (jamais transmis
# hors de la plage validée) plutôt que de risquer un signal que ces ESC
# n'ont jamais été testés pour comprendre.
ESC_BIDIRECTIONAL = False

# --------------------------------------------------------------------------
# Armement ESC
# --------------------------------------------------------------------------
# La plupart des ESC hobby exigent un signal neutre tenu quelques secondes
# après la mise sous tension avant d'accepter une commande — sinon ils
# restent en attente d'armement. La durée exacte dépend de la marque ; à
# confirmer au premier essai réel (même philosophie que docs/calibration.md :
# un point qui ne se devine pas, isolé dans un seul endroit facile à corriger).
ESC_ARM_DURATION_S = 2.0
