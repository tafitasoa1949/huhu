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
ESC_PIN = 12  # broche physique 32 (BCM 12) — signal accélération vers l'ESC, câblage confirmé
STEERING_PIN = 13  # broche physique 33 (BCM 13) — signal direction vers le servo, câblage à confirmer

# --------------------------------------------------------------------------
# Cadence du signal (standard hobby RC : 50 Hz, une impulsion toutes les 20 ms)
# --------------------------------------------------------------------------
PWM_FREQUENCY_HZ = 50

# --------------------------------------------------------------------------
# Plage utile de l'ESC — mesurée au banc, PAS la plage hobby générique
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
ESC_MIN_PULSE_US = 900  # arrêt / neutre d'armement — marge sous le seuil réel de l'ESC
ESC_MAX_PULSE_US = 1200  # plein régime avant

# Le servo de direction, lui, est un servo hobby ordinaire : plage complète,
# centré au milieu. Rien à voir avec la plage étroite de l'ESC ci-dessus —
# d'où deux réglages séparés plutôt qu'un seul partagé.
STEERING_MIN_PULSE_US = 1000  # butée gauche
STEERING_MAX_PULSE_US = 2000  # butée droite

# --------------------------------------------------------------------------
# Sens de rotation / de braquage
# --------------------------------------------------------------------------
# À valider roues levées avant tout essai au sol, comme pour l'ancien
# châssis différentiel (docs/calibration.md). Si le sens réel est inversé,
# basculer la valeur ici plutôt que d'inverser les fils du signal.
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
# `GpioMotorDriver` arme et arrête l'ESC au bon neutre selon cette valeur, et
# un `speed_pct` négatif est ramené à l'arrêt (jamais transmis hors de la
# plage validée) plutôt que de risquer un signal que cet ESC n'a jamais été
# testé pour comprendre.
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
