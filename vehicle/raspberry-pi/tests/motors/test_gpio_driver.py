"""Teste `GpioMotorDriver` sans matériel via `gpiozero.pins.mock.MockFactory`
— aucun Raspberry Pi requis, même principe que le mode `virtual` déjà
utilisé côté ESP32 (docs/communication-protocol.md, §8)."""

import pytest
from gpiozero.pins.mock import MockFactory, MockPWMPin

from smart_car.config import hardware
from smart_car.motors.gpio_driver import GpioMotorDriver


@pytest.fixture
def driver():
    # `MockPin` par défaut n'émule pas le PWM (`Servo` en a besoin) —
    # `MockPWMPin` le fait, sans matériel ni Raspberry Pi.
    factory = MockFactory(pin_class=MockPWMPin)
    d = GpioMotorDriver(esc_pin=18, steering_pin=13, pin_factory=factory, arm=False)
    yield d
    d.close()


def test_neutral_at_startup(driver):
    assert driver._esc.value == pytest.approx(0.0)
    assert driver._steering.value == pytest.approx(0.0)


def test_full_forward_maps_to_positive_one(driver):
    driver.apply(100, 0)
    assert driver._esc.value == pytest.approx(1.0)


def test_full_reverse_maps_to_negative_one(driver):
    driver.apply(-100, 0)
    assert driver._esc.value == pytest.approx(-1.0)


def test_half_speed_maps_to_half_unit(driver):
    driver.apply(50, 0)
    assert driver._esc.value == pytest.approx(0.5)


def test_steering_is_independent_of_speed(driver):
    driver.apply(30, -70)
    assert driver._esc.value == pytest.approx(0.3)
    assert driver._steering.value == pytest.approx(-0.7)


def test_stop_returns_both_channels_to_neutral(driver):
    driver.apply(80, -40)
    driver.stop()
    assert driver._esc.value == pytest.approx(0.0)
    assert driver._steering.value == pytest.approx(0.0)


def test_invert_flips_sign(monkeypatch):
    monkeypatch.setattr(hardware, "ESC_INVERT", True)
    factory = MockFactory(pin_class=MockPWMPin)
    d = GpioMotorDriver(esc_pin=18, steering_pin=13, pin_factory=factory, arm=False)
    try:
        d.apply(60, 0)
        assert d._esc.value == pytest.approx(-0.6)
    finally:
        d.close()
