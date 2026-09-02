"""Brochage et calibration matérielle — le seul fichier à corriger le jour
du câblage réel, même rôle que l'ancien `esp32-controller/include/pin_config.h`
(docs/calibration.md : « un seul fichier à corriger, aucun autre ne doit
contenir de numéro de broche »).

Toutes les valeurs sont provisoires tant que le châssis ESC + servo n'est pas
monté.
"""

# --------------------------------------------------------------------------
# Brochage GPIO (BCM)
# --------------------------------------------------------------------------
ESC_PIN = 18  # PWM matériel — signal accélération vers l'ESC
STEERING_PIN = 13  # PWM matériel — signal direction vers le servo

# --------------------------------------------------------------------------
# Signal PWM (standard hobby RC : 50 Hz, impulsion 1000-2000 µs)
# --------------------------------------------------------------------------
PWM_MIN_PULSE_S = 0.001  # 1000 µs
PWM_MAX_PULSE_S = 0.002  # 2000 µs
PWM_FRAME_WIDTH_S = 1 / 50  # 20 ms, 50 Hz

# --------------------------------------------------------------------------
# Sens de rotation / de braquage
# --------------------------------------------------------------------------
# À valider roues levées avant tout essai au sol, comme pour l'ancien
# châssis différentiel (docs/calibration.md). Si le sens réel est inversé,
# basculer la valeur ici plutôt que d'inverser les fils du signal.
ESC_INVERT = False
STEERING_INVERT = False

# --------------------------------------------------------------------------
# Armement ESC
# --------------------------------------------------------------------------
# La plupart des ESC hobby exigent un signal neutre tenu quelques secondes
# après la mise sous tension avant d'accepter une commande — sinon ils
# restent en attente d'armement. La durée exacte dépend de la marque ; à
# confirmer au premier essai réel (même philosophie que docs/calibration.md :
# un point qui ne se devine pas, isolé dans un seul endroit facile à corriger).
ESC_ARM_DURATION_S = 2.0
