"""Pilotage matériel réel — ESC + servo via `gpiozero` (PWM).

`gpiozero.Servo` attend une commande dans [-1, 1] sur un signal 50 Hz /
1000-2000 µs — exactement le format qu'un ESC hobby attend (il se pilote
comme un servo) et celui qu'attend un servo de direction. `speed_pct` pilote
l'ESC, `steering_pct` pilote le servo, indépendamment : il n'y a pas de
mélange différentiel à faire (voir `driver.py`).

`pin_factory` est exposé pour les tests (`gpiozero.pins.mock.MockFactory`) :
sans lui, `gpiozero` tente d'accéder au GPIO réel et échoue hors d'un
Raspberry Pi.
"""

from __future__ import annotations

import time

from gpiozero import Servo

from smart_car.config import hardware
from smart_car.motors.driver import MotorDriver


def _pct_to_unit(value_pct: int, invert: bool) -> float:
    unit = max(-100, min(100, value_pct)) / 100.0
    return -unit if invert else unit


class GpioMotorDriver(MotorDriver):
    def __init__(
        self,
        *,
        esc_pin: int = hardware.ESC_PIN,
        steering_pin: int = hardware.STEERING_PIN,
        pin_factory=None,
        arm: bool = True,
    ) -> None:
        self._esc = Servo(
            esc_pin,
            min_pulse_width=hardware.PWM_MIN_PULSE_S,
            max_pulse_width=hardware.PWM_MAX_PULSE_S,
            frame_width=hardware.PWM_FRAME_WIDTH_S,
            pin_factory=pin_factory,
        )
        self._steering = Servo(
            steering_pin,
            min_pulse_width=hardware.PWM_MIN_PULSE_S,
            max_pulse_width=hardware.PWM_MAX_PULSE_S,
            frame_width=hardware.PWM_FRAME_WIDTH_S,
            pin_factory=pin_factory,
        )
        self._esc.value = 0.0
        self._steering.value = 0.0
        if arm:
            self._arm_esc()

    def _arm_esc(self) -> None:
        # Neutre tenu quelques secondes après la mise sous tension : la
        # plupart des ESC hobby n'acceptent pas de commande avant ça (voir
        # config/hardware.py, ESC_ARM_DURATION_S).
        time.sleep(hardware.ESC_ARM_DURATION_S)

    def apply(self, speed_pct: int, steering_pct: int) -> None:
        self._esc.value = _pct_to_unit(speed_pct, hardware.ESC_INVERT)
        self._steering.value = _pct_to_unit(steering_pct, hardware.STEERING_INVERT)

    def stop(self) -> None:
        self.apply(0, 0)

    def close(self) -> None:
        self._esc.close()
        self._steering.close()
