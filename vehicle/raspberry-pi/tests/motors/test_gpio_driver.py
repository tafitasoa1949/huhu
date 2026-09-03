"""Teste `GpioMotorDriver` sans matériel : une doublure d'émetteur
d'impulsions suffit à vérifier toute la conversion `speed_pct` -> µs, qui est
la seule chose que ce module décide. Aucun Raspberry Pi requis, même principe
que le mode `virtual` côté ESP32 (docs/communication-protocol.md, §8).

Les assertions portent sur des **microsecondes**, c'est-à-dire exactement ce
qui part sur le fil vers l'ESC — pas sur une abstraction intermédiaire.
"""

import pytest

from smart_car.config import hardware
from smart_car.motors.gpio_driver import GpioMotorDriver, _esc_pulse_us

STEERING_PIN_FOR_TEST = hardware.STEERING_PIN  # GPIO18, servo de direction câblé


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
# Le servo de direction a sa propre plage, 500-2300 µs (mesurée au banc), donc
# un centre à 1400 µs — pas 1500. Sans rapport avec la plage des ESC.


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


def test_no_steering_pin_configured_means_nothing_is_sent_for_steering(sender):
    # `steering_pin=None` (aucun servo câblé) : le pilote ne doit revendiquer
    # ni piloter aucune broche pour la direction. C'était la configuration
    # réelle avant le montage du servo, et ça doit rester propre.
    driver = GpioMotorDriver(pulse_sender=sender, steering_pin=None, arm=False)
    driver.apply(0, 100)
    assert set(sender.pulses) == {hardware.ESC_PIN, hardware.ESC2_PIN}


def test_steering_uses_its_own_full_range_independent_of_the_esc(driver, sender):
    # Plage propre au servo (500-2300 µs), sans rapport avec la plage étroite
    # des ESC. Gauche = négatif, droite = positif (docs/contracts.md).
    driver.apply(0, -100)
    assert sender.steering == 500
    driver.apply(0, 100)
    assert sender.steering == 2300
    driver.apply(0, 0)
    assert sender.steering == 1400  # centre = milieu de 500-2300, pas 1500


def test_speed_and_steering_are_independent(driver, sender):
    driver.apply(50, -70)
    assert sender.esc == 1050
    assert sender.esc2 == 1050
    assert sender.steering == 770


def test_an_unchanged_command_is_not_re_sent(driver, sender):
    # Régression : le watchdog de sécurité appelle `apply(0, 0)` toutes les
    # 50 ms dès qu'aucune commande n'arrive. Chaque réémission relançait le
    # minutage logiciel du signal ; le servo, re-commandé 20 fois par
    # seconde, chassait en permanence au lieu de se poser.
    driver.apply(40, 25)
    sender.call_order.clear()

    for _ in range(10):
        driver.apply(40, 25)

    assert sender.call_order == []


def test_a_changed_command_is_sent_again(driver, sender):
    driver.apply(40, 25)
    sender.call_order.clear()

    driver.apply(41, 25)  # vitesse seule modifiée

    assert sender.call_order == [hardware.ESC_PIN, hardware.ESC2_PIN]
    assert sender.esc == _esc_pulse_us(41)


def test_releasing_the_steering_joystick_returns_the_servo_to_centre(driver, sender):
    # Manche relâché -> steering_pct = 0 -> milieu de plage, c'est-à-dire la
    # position posée au démarrage. Le servo revient à son point de départ.
    centre_us = sender.steering
    driver.apply(0, 100)
    assert sender.steering == 2300

    driver.apply(0, 0)
    assert sender.steering == 1400
    assert sender.steering == centre_us


def test_pulses_are_sent_at_the_configured_frequency(driver, sender):
    driver.apply(40, 0)
    assert set(sender.frequencies) == {hardware.PWM_FREQUENCY_HZ}


def test_stop_returns_every_channel_to_neutral(driver, sender):
    driver.apply(80, -40)
    driver.stop()
    assert sender.esc == 900
    assert sender.esc2 == 900
    assert sender.steering == 1400  # roues droites


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
    # Le côté physique qui correspond à l'impulsion minimale dépend du
    # montage du palonnier : ce réglage est là pour le corriger sans
    # démonter (voir config/hardware.py, STEERING_INVERT).
    monkeypatch.setattr(hardware, "STEERING_INVERT", True)
    driver = GpioMotorDriver(pulse_sender=sender, arm=False)
    driver.apply(0, 100)
    assert sender.steering == 500


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
