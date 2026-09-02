from __future__ import annotations

import pytest

from smart_car_gateway.registry import CarAlreadyClaimedError, CarRegistry, CarUnknownError


def make_registry(now: list[float], claim_fn=None):
    return CarRegistry(
        claim_fn=claim_fn or (lambda car: ("tok-123", 30)),
        clock=lambda: now[0],
    )


def register_car01(registry: CarRegistry) -> None:
    registry.register(
        car_id="car-01",
        name="Smart RC Car #1",
        ip="192.168.4.23",
        control_port=5005,
        telemetry_port=5006,
        video_port=5007,
        mgmt_port=9000,
    )


def test_unregistered_car_is_absent_from_list():
    registry = make_registry([0.0])
    assert registry.list_cars() == []


def test_registered_car_is_online_right_after_heartbeat():
    now = [0.0]
    registry = make_registry(now)
    register_car01(registry)

    [(car, online)] = registry.list_cars()
    assert car.car_id == "car-01"
    assert online is True


def test_car_goes_offline_after_heartbeat_timeout():
    now = [0.0]
    registry = make_registry(now)
    register_car01(registry)

    now[0] = 11.0  # > HEARTBEAT_TIMEOUT_S (10s)
    [(_, online)] = registry.list_cars()
    assert online is False


def test_heartbeat_refreshes_online_status():
    now = [0.0]
    registry = make_registry(now)
    register_car01(registry)

    now[0] = 9.0
    registry.heartbeat("car-01")
    now[0] = 18.0  # 9s après le heartbeat, toujours < 10s
    [(_, online)] = registry.list_cars()
    assert online is True


def test_heartbeat_on_unknown_car_raises():
    registry = make_registry([0.0])
    with pytest.raises(CarUnknownError):
        registry.heartbeat("car-99")


def test_claim_calls_car_and_returns_full_session():
    now = [0.0]
    registry = make_registry(now, claim_fn=lambda car: ("tok-abc", 30))
    register_car01(registry)

    session = registry.claim("car-01")
    assert session == {
        "car_id": "car-01",
        "ip": "192.168.4.23",
        "control_port": 5005,
        "telemetry_port": 5006,
        "video_port": 5007,
        "token": "tok-abc",
        "expires_in_s": 30,
    }


def test_claim_unknown_car_raises():
    registry = make_registry([0.0])
    with pytest.raises(CarUnknownError):
        registry.claim("car-01")


def test_claim_offline_car_raises_unknown_not_already_claimed():
    now = [0.0]
    registry = make_registry(now)
    register_car01(registry)
    now[0] = 999.0  # heartbeat expiré

    with pytest.raises(CarUnknownError):
        registry.claim("car-01")


def test_second_claim_before_expiry_raises_already_claimed():
    now = [0.0]
    registry = make_registry(now)
    register_car01(registry)

    registry.claim("car-01")
    with pytest.raises(CarAlreadyClaimedError):
        registry.claim("car-01")


def test_claim_available_again_after_expiry():
    now = [0.0]
    registry = make_registry(now)
    register_car01(registry)

    registry.claim("car-01")
    now[0] = 31.0  # > expires_in_s (30)
    registry.heartbeat("car-01")  # la voiture continue d'émettre pendant ce temps
    # Ne doit pas lever : le jeton précédent est périmé.
    registry.claim("car-01")


def test_reregistering_a_car_preserves_active_claim():
    now = [0.0]
    registry = make_registry(now)
    register_car01(registry)
    registry.claim("car-01")

    register_car01(registry)  # ex: redémarrage voiture, IP DHCP inchangée
    with pytest.raises(CarAlreadyClaimedError):
        registry.claim("car-01")


def test_claim_fn_failure_does_not_mark_car_as_claimed():
    now = [0.0]

    def failing_claim(car):
        raise RuntimeError("voiture injoignable")

    registry = make_registry(now, claim_fn=failing_claim)
    register_car01(registry)

    with pytest.raises(RuntimeError):
        registry.claim("car-01")

    # Un second essai retombe sur la même erreur réseau, pas sur
    # CarAlreadyClaimedError : la voiture n'a pas été marquée revendiquée
    # pour un jeton qu'elle n'a jamais émis.
    with pytest.raises(RuntimeError):
        registry.claim("car-01")
