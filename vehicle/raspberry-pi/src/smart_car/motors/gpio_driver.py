"""Pilotage matériel réel — ESC + servo, impulsions envoyées via `lgpio`.

Un ESC comme un servo se pilotent par la **largeur d'impulsion** (en µs) d'un
signal à 50 Hz. Ce module raisonne donc directement en microsecondes, avec
`lgpio.tx_servo`, et non en rapport cyclique.

**Pourquoi pas `gpiozero.Servo`** (l'implémentation précédente) : sur Pi 5,
`gpiozero` passe par `LGPIOFactory`, dont `_set_state` tronque le rapport
cyclique à l'entier de pourcent (`int(value * 100)`) avant de le transmettre.
À 50 Hz, 1 % = 200 µs : sur la plage utile de cet ESC (1000-1200 µs, voir
`config/hardware.py`), il ne restait que **deux** valeurs possibles — arrêt,
ou plein régime. Le joystick était binaire, et toute position intermédiaire
retombait sur l'arrêt. `lgpio.tx_servo` prend la largeur d'impulsion en µs
directement : 200 paliers au lieu de 2, sans overlay ni redémarrage.

`hardware.ESC_BIDIRECTIONAL` choisit la convention de neutre de l'ESC câblé :
un ESC unidirectionnel (le cas ici, confirmé au banc) n'a pas de marche
arrière, contrairement à ce que `docs/mobile-protocol.md` permet pour
`speed_pct`. Un `speed_pct` négatif y est ramené à l'arrêt plutôt que
transmis sous l'impulsion minimale — hors de la plage validée sur cet ESC.

`pulse_sender` est exposé pour les tests : une doublure suffit à vérifier
toute la conversion `speed_pct` -> µs sans matériel ni Raspberry Pi.

**Pi 5** : `lgpio` vient de `apt install python3-lgpio` (déjà présent sur
Raspberry Pi OS récent), pas de `pip install lgpio` qui exige de compiler une
extension C (`swig`). Le `.venv` doit donc voir les paquets système :
`include-system-site-packages = true` dans `.venv/pyvenv.cfg`.

Limite connue : `lgpio.tx_servo` reste un signal *logiciel*, pas le PWM
matériel du Pi 5 (overlay `pwm-2chan`, non activé ici — demande un `sudo` sur
`config.txt` et un redémarrage). La résolution est désormais fine, mais une
gigue de minutage subsiste ; si elle se fait sentir en conduite, c'est cette
piste-là qu'il faudra suivre.
"""

from __future__ import annotations

import os
import time
from typing import Callable

from smart_car.config import hardware
from smart_car.motors.driver import MotorDriver

# Signature d'un émetteur d'impulsions : (broche BCM, largeur µs, fréquence Hz).
PulseSender = Callable[[int, int, int], None]


def _esc_pulse_us(speed_pct: int) -> int:
    """`speed_pct` -> largeur d'impulsion, dans la plage réelle de l'ESC."""
    span = hardware.ESC_MAX_PULSE_US - hardware.ESC_MIN_PULSE_US
    if hardware.ESC_BIDIRECTIONAL:
        clamped = max(-100, min(100, speed_pct))
        if hardware.ESC_INVERT:
            clamped = -clamped
        return round(hardware.ESC_MIN_PULSE_US + (clamped + 100) / 200 * span)
    # Unidirectionnel : pas de marche arrière (voir `hardware.ESC_BIDIRECTIONAL`).
    # `ESC_INVERT` ne s'applique pas — sur un brushless, le sens de rotation se
    # corrige en permutant deux fils de phase (docs/calibration.md), pas par le
    # signe d'un signal qui n'a ici qu'un sens (arrêt -> plein régime).
    clamped = max(0, min(100, speed_pct))
    return round(hardware.ESC_MIN_PULSE_US + clamped / 100 * span)


def _steering_pulse_us(steering_pct: int) -> int:
    """`steering_pct` -> largeur d'impulsion, servo centré sur le milieu de sa plage."""
    clamped = max(-100, min(100, steering_pct))
    if hardware.STEERING_INVERT:
        clamped = -clamped
    span = hardware.STEERING_MAX_PULSE_US - hardware.STEERING_MIN_PULSE_US
    return round(hardware.STEERING_MIN_PULSE_US + (clamped + 100) / 200 * span)


class LgpioPulseSender:
    """Émetteur réel : réserve les broches et envoie les impulsions via `lgpio`."""

    def __init__(self, chip: int | None = None) -> None:
        import lgpio

        self._lgpio = lgpio
        # Même détection que `gpiozero.pins.lgpio` : le Pi 5 expose ses GPIO
        # sur gpiochip4 (RP1), les modèles antérieurs sur gpiochip0.
        if chip is None:
            chip = 4 if os.path.exists("/dev/gpiochip4") else 0
        self._handle = lgpio.gpiochip_open(chip)
        self._claimed: set[int] = set()

    def __call__(self, pin: int, pulse_us: int, frequency_hz: int) -> None:
        if pin not in self._claimed:
            self._lgpio.gpio_claim_output(self._handle, pin)
            self._claimed.add(pin)
        self._lgpio.tx_servo(self._handle, pin, int(pulse_us), int(frequency_hz))

    def close(self) -> None:
        for pin in self._claimed:
            # 0 = plus aucune impulsion. L'ESC verra une perte de signal et
            # coupera de lui-même, ce qui est le repli sûr.
            self._lgpio.tx_servo(self._handle, pin, 0)
        self._claimed.clear()
        self._lgpio.gpiochip_close(self._handle)


class GpioMotorDriver(MotorDriver):
    def __init__(
        self,
        *,
        esc_pin: int = hardware.ESC_PIN,
        steering_pin: int = hardware.STEERING_PIN,
        pulse_sender: PulseSender | None = None,
        arm: bool = True,
    ) -> None:
        self._esc_pin = esc_pin
        self._steering_pin = steering_pin
        self._sender = pulse_sender if pulse_sender is not None else LgpioPulseSender()
        self._owns_sender = pulse_sender is None

        # Neutre sur les deux voies avant toute commande : pour l'ESC c'est
        # aussi le signal d'armement (impulsion minimale en unidirectionnel,
        # milieu de plage en bidirectionnel — `_esc_pulse_us(0)` s'en charge).
        self.apply(0, 0)
        if arm:
            self._arm_esc()

    def _arm_esc(self) -> None:
        # Neutre tenu quelques secondes après la mise sous tension : la
        # plupart des ESC hobby n'acceptent pas de commande avant ça (voir
        # config/hardware.py, ESC_ARM_DURATION_S).
        time.sleep(hardware.ESC_ARM_DURATION_S)

    def apply(self, speed_pct: int, steering_pct: int) -> None:
        self._sender(self._esc_pin, _esc_pulse_us(speed_pct), hardware.PWM_FREQUENCY_HZ)
        self._sender(self._steering_pin, _steering_pulse_us(steering_pct), hardware.PWM_FREQUENCY_HZ)

    def stop(self) -> None:
        self.apply(0, 0)

    def close(self) -> None:
        self.stop()
        if self._owns_sender:
            self._sender.close()
