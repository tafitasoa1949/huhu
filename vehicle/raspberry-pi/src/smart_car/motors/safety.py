"""Arbitrage de sécurité — canal P2P téléphone ↔ Raspberry Pi.

Remplace l'arbitrage qui vivait dans `esp32-controller/src/safety.cpp` :
depuis que l'ESC/servo sont pilotés directement en GPIO par le Raspberry Pi
(plus d'ESP32-controller intermédiaire), il n'y a plus de second niveau de
sécurité côté firmware — celui-ci doit être strict et ne dépendre de rien
d'autre.

Fonctions pures, testables sans réseau ni GPIO — même esprit que
`safety.cpp`/`steering_controller.cpp`.
"""

from __future__ import annotations

from dataclasses import dataclass

# docs/mobile-protocol.md, règle NFR : silence > 2000 ms sur le canal de
# contrôle -> arrêt, indépendamment de ce qui se passe côté app.
CONTROL_TIMEOUT_MS = 2000


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


@dataclass(frozen=True)
class DriveDecision:
    speed_pct: int
    steering_pct: int
    stopped_reason: str | None  # None = conduite normale, sinon cause de l'arrêt


def decide(
    *,
    requested_speed_pct: int,
    requested_steering_pct: int,
    emergency: bool,
    physical_estop_engaged: bool,
    ms_since_last_valid_packet: float,
) -> DriveDecision:
    """Arbitre la commande à réellement appliquer.

    Priorité décroissante (même ordre que l'ancien `safety.cpp`) :

    1. bouton d'arrêt d'urgence physique (s'il est câblé) ;
    2. `emergency=true` dans le dernier paquet valide ;
    3. silence de plus de `CONTROL_TIMEOUT_MS` sur le canal de contrôle ;
    4. conduite normale, valeurs bornées à [-100, 100].
    """
    if physical_estop_engaged:
        return DriveDecision(0, 0, "PHYSICAL_ESTOP")
    if emergency:
        return DriveDecision(0, 0, "EMERGENCY_COMMAND")
    if ms_since_last_valid_packet > CONTROL_TIMEOUT_MS:
        return DriveDecision(0, 0, "CONTROL_TIMEOUT")

    speed = clamp(requested_speed_pct, -100, 100)
    steering = clamp(requested_steering_pct, -100, 100)
    return DriveDecision(speed, steering, None)
