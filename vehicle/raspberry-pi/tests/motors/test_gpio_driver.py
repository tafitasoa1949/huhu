"""Teste `GpioMotorDriver` sans matériel : une doublure d'émetteur
d'impulsions suffit à vérifier toute la conversion `speed_pct` -> µs, qui est
la seule chose que ce module décide. Aucun Raspberry Pi requis, même principe
que le mode `virtual` côté ESP32 (docs/communication-protocol.md, §8).

Les assertions portent sur des **microsecondes**, c'est-à-dire exactement ce
qui part sur le fil vers l'ESC — pas sur une abstraction intermédiaire.
"""

import pytest

from smart_car.config import hardware
from smart_car.motors.gpio_driver import GpioMotorDriver

STEERING_PIN_FOR_TEST = 18  # hardware.STEERING_PIN vaut None par défaut (pas de servo câblé)


class RecordingSender:
    """Doublure d'émetteur : retient la dernière impulsion par broche, et
    l'ordre dans lequel les broches ont été appelées la dernière fois."""

    def __init__(self) -> None:
        self.pulses: dict[int, int] = {}
        self.frequencies: list[int] = []
        self.call_order: list[int] = []
        self.closed = False

    def __call__(self, pin: int, pulse_us: int, frequency_hz: int) -> None:
        self.pulses[pin] = pulse_us
        self.frequencies.append(frequency_hz)
        self.call_order.append(pin)

    def close(self) -> None:
        self.closed = True

    @property
    def esc(self) -> int:
        return self.pulses[hardware.ESC_PIN]

    @property
    def esc2(self) -> int:
        return self.pulses[hardware.ESC2_PIN]

    @property
    def steering(self) -> int:
        return self.pulses[STEERING_PIN_FOR_TEST]


@pytest.fixture
def sender():
    return RecordingSender()


@pytest.fixture
def driver(sender):
    return GpioMotorDriver(pulse_sender=sender, arm=False)


# ESC unidirectionnel de plage 900-1200 µs : c'est le moteur réellement
# câblé, mesuré au banc (voir config/hardware.py — le point bas n'est pas
# 1000 µs standard, mais 900 µs, marge de sécurité sous le seuil réel de cet
# ESC). Comportement par défaut, donc testé tel quel sans monkeypatch.
#
# Pas de servo de direction câblé par défaut (hardware.STEERING_PIN = None) :
# les tests qui portent sur la direction injectent explicitement
# `steering_pin=STEERING_PIN_FOR_TEST`.


def test_neutral_at_startup_is_the_stop_pulse_on_both_motors(driver, sender):
    # Le constructeur envoie le neutre avant toute commande — c'est aussi le
    # signal d'armement des deux ESC, envoyés ensemble.
    assert sender.esc == hardware.ESC_MIN_PULSE_US
    assert sender.esc2 == hardware.ESC_MIN_PULSE_US


def test_both_propulsion_motors_receive_the_same_pulse_in_tandem(driver, sender):
    # Pas de mélange différentiel gauche/droite : les deux ESC de propulsion
    # tournent en tandem sur la même commande de vitesse (câblage confirmé :
    # les deux broches sont dédiées à la propulsion, aucun servo câblé).
    for speed_pct in (0, 1, 25, 50, 75, 99, 100):
        driver.apply(speed_pct, 0)
        assert sender.esc == sender.esc2, f"speed_pct={speed_pct}"


def test_full_forward_maps_to_the_esc_real_maximum_not_the_hobby_standard(driver, sender):
    # Régression : 100 % envoyait 2000 µs (standard hobby générique), très
    # au-delà de ce que cet ESC interprète — le moteur bourdonnait sans
    # jamais tourner. Le maximum réel est 1200 µs.
    driver.apply(100, 0)
    assert sender.esc == 1200
    assert sender.esc == hardware.ESC_MAX_PULSE_US


def test_zero_speed_maps_to_the_stop_pulse(driver, sender):
    driver.apply(0, 0)
    assert sender.esc == 900


def test_intermediate_speeds_are_proportional_not_collapsed_to_two_levels(driver, sender):
    # Régression : `gpiozero` tronquait le rapport cyclique à l'entier de
    # pourcent (200 µs de pas à 50 Hz), ce qui écrasait toute la plage
    # 900-1200 µs sur deux valeurs — le joystick devenait tout ou rien.
    expected = {0: 900, 25: 975, 50: 1050, 75: 1125, 100: 1200}
    for speed_pct, pulse_us in expected.items():
        driver.apply(speed_pct, 0)
        assert sender.esc == pulse_us, f"speed_pct={speed_pct}"


def test_one_percent_of_joystick_still_changes_the_pulse(driver, sender):
    driver.apply(1, 0)
    assert sender.esc == 903


def test_negative_speed_is_clamped_to_stop_not_sent_below_the_minimum(driver, sender):
    # Le protocole autorise un speed_pct négatif (marche arrière, pensé pour
    # un ESC bidirectionnel — docs/mobile-protocol.md) ; ces moteurs n'en ont
    # pas.
    driver.apply(-100, 0)
    assert sender.esc == hardware.ESC_MIN_PULSE_US
    assert sender.esc2 == hardware.ESC_MIN_PULSE_US


def test_no_steering_pin_configured_means_nothing_is_sent_for_steering(driver, sender):
    # hardware.STEERING_PIN vaut None : aucun servo câblé pour l'instant. Le
    # pilote ne doit revendiquer/piloter aucune broche pour la direction.
    driver.apply(0, 100)
    assert STEERING_PIN_FOR_TEST not in sender.pulses
    assert set(sender.pulses) == {hardware.ESC_PIN, hardware.ESC2_PIN}


def test_steering_uses_its_own_full_range_independent_of_the_esc(sender):
    # Le servo de direction est un servo hobby ordinaire : plage complète
    # 1000-2000 µs, sans rapport avec la plage étroite de l'ESC. Broche
    # explicite : hardware.STEERING_PIN vaut None par défaut.
    driver = GpioMotorDriver(pulse_sender=sender, steering_pin=STEERING_PIN_FOR_TEST, arm=False)
    driver.apply(0, -100)
    assert sender.steering == 1000
    driver.apply(0, 100)
    assert sender.steering == 2000
    driver.apply(0, 0)
    assert sender.steering == 1500


def test_speed_and_steering_are_independent(sender):
    driver = GpioMotorDriver(pulse_sender=sender, steering_pin=STEERING_PIN_FOR_TEST, arm=False)
    driver.apply(50, -70)
    assert sender.esc == 1050
    assert sender.esc2 == 1050
    assert sender.steering == 1150


def test_pulses_are_sent_at_the_configured_frequency(driver, sender):
    driver.apply(40, 0)
    assert set(sender.frequencies) == {hardware.PWM_FREQUENCY_HZ}


def test_stop_returns_every_channel_to_neutral(sender):
    driver = GpioMotorDriver(pulse_sender=sender, steering_pin=STEERING_PIN_FOR_TEST, arm=False)
    driver.apply(80, -40)
    driver.stop()
    assert sender.esc == 900
    assert sender.esc2 == 900
    assert sender.steering == 1500


def test_close_does_not_touch_an_injected_sender(driver, sender):
    # L'émetteur injecté appartient à l'appelant (les tests) : le pilote ne
    # doit pas le fermer sous ses pieds.
    driver.close()
    assert sender.closed is False
    assert sender.esc == 900
    assert sender.esc2 == 900


def test_esc_invert_has_no_effect_on_a_unidirectional_esc(monkeypatch, sender):
    # Sur un brushless, le sens de rotation se corrige en permutant deux fils
    # de phase (docs/calibration.md), pas via le signe d'un signal qui n'a
    # ici qu'un sens.
    monkeypatch.setattr(hardware, "ESC_INVERT", True)
    driver = GpioMotorDriver(pulse_sender=sender, arm=False)
    driver.apply(60, 0)
    assert sender.esc == 1080
    assert sender.esc2 == 1080


def test_steering_invert_flips_the_servo(monkeypatch, sender):
    monkeypatch.setattr(hardware, "STEERING_INVERT", True)
    driver = GpioMotorDriver(pulse_sender=sender, steering_pin=STEERING_PIN_FOR_TEST, arm=False)
    driver.apply(0, 100)
    assert sender.steering == 1000


class TestBidirectionalEsc:
    """Comportement de repli si `hardware.ESC_BIDIRECTIONAL` repasse à True —
    un futur ESC compatible marche arrière, par exemple. Pas le moteur câblé
    aujourd'hui, mais un mode que le code doit continuer de produire
    correctement."""

    @pytest.fixture(autouse=True)
    def bidirectional(self, monkeypatch):
        monkeypatch.setattr(hardware, "ESC_BIDIRECTIONAL", True)

    def test_neutral_at_startup_is_the_middle_of_the_range(self, sender):
        GpioMotorDriver(pulse_sender=sender, arm=False)
        assert sender.esc == 1050  # milieu de 900-1200
        assert sender.esc2 == 1050

    def test_full_reverse_maps_to_the_minimum(self, driver, sender):
        driver.apply(-100, 0)
        assert sender.esc == 900

    def test_full_forward_maps_to_the_maximum(self, driver, sender):
        driver.apply(100, 0)
        assert sender.esc == 1200

    def test_invert_flips_the_sign(self, monkeypatch, sender):
        monkeypatch.setattr(hardware, "ESC_INVERT", True)
        driver = GpioMotorDriver(pulse_sender=sender, arm=False)
        driver.apply(100, 0)
        assert sender.esc == 900
