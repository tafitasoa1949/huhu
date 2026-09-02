"""Interface de pilotage moteur — un canal accélération (ESC), un canal
direction (servo).

Remplace le pont en H différentiel autrefois piloté en série par
l'ESP32-controller (`vehicle/esp32-controller/`) : le châssis retenu est un
ESC + servo de direction classiques, câblés directement sur les GPIO du
Raspberry Pi. Il n'y a donc plus de mélange différentiel gauche/droite à
faire ici, contrairement à `steering_controller.cpp`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class MotorDriver(ABC):
    @abstractmethod
    def apply(self, speed_pct: int, steering_pct: int) -> None:
        """speed_pct : -100 (pleine marche arrière) à 100 (pleine marche avant).
        steering_pct : -100 (gauche) à 100 (droite)."""

    @abstractmethod
    def stop(self) -> None:
        """Position neutre immédiate — appelé par l'arbitrage de sécurité."""

    def close(self) -> None:
        """Libère les ressources matérielles. No-op par défaut (simulateur)."""


class SimulatedMotorDriver(MotorDriver):
    """N'actionne rien, journalise ce qui aurait été envoyé — mode
    `smart-car-server --simulate`, pour valider la chaîne réseau complète
    sans matériel avant le montage."""

    def __init__(self) -> None:
        self.last_speed_pct = 0
        self.last_steering_pct = 0
        self._last_logged: tuple[int, int] | None = None

    def apply(self, speed_pct: int, steering_pct: int) -> None:
        self.last_speed_pct = speed_pct
        self.last_steering_pct = steering_pct
        # Journalisé seulement quand la consigne change : le watchdog de
        # sécurité ré-applique l'arrêt à chaque tick (20 Hz), ce qui noyait
        # le journal sous des lignes identiques et rendait illisible la seule
        # chose qu'on y cherche en test manuel — la commande qui arrive.
        if (speed_pct, steering_pct) != self._last_logged:
            self._last_logged = (speed_pct, steering_pct)
            print(f"[SimulatedMotorDriver] speed={speed_pct:+d}%  steering={steering_pct:+d}%")

    def stop(self) -> None:
        self.apply(0, 0)
