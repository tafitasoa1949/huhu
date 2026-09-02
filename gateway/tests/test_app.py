from __future__ import annotations

import pytest

from smart_car_gateway.app import create_app
from smart_car_gateway.registry import CarRegistry


@pytest.fixture
def client():
    now = [0.0]
    registry = CarRegistry(claim_fn=lambda car: ("tok-abc", 30), clock=lambda: now[0])
    app = create_app(registry)
    app.config["TESTING"] = True
    return app.test_client()


def register_car01(client):
    return client.post(
        "/api/cars/register",
        json={
            "car_id": "car-01",
            "name": "Smart RC Car #1",
            "ip": "192.168.4.23",
            "control_port": 5005,
            "telemetry_port": 5006,
            "video_port": 5007,
            "mgmt_port": 9000,
        },
    )


def test_list_cars_empty_initially(client):
    response = client.get("/api/cars")
    assert response.status_code == 200
    assert response.get_json() == []


def test_register_then_list_shows_online_car(client):
    assert register_car01(client).status_code == 204

    response = client.get("/api/cars")
    assert response.status_code == 200
    assert response.get_json() == [{"car_id": "car-01", "name": "Smart RC Car #1", "online": True}]


def test_claim_returns_full_session_matching_kotlin_dto_fields(client):
    register_car01(client)

    response = client.post("/api/cars/car-01/claim")
    assert response.status_code == 200
    body = response.get_json()
    assert body == {
        "car_id": "car-01",
        "ip": "192.168.4.23",
        "control_port": 5005,
        "telemetry_port": 5006,
        "video_port": 5007,
        "token": "tok-abc",
        "expires_in_s": 30,
    }


def test_claim_unknown_car_returns_404(client):
    response = client.post("/api/cars/car-99/claim")
    assert response.status_code == 404


def test_second_claim_returns_409(client):
    register_car01(client)
    client.post("/api/cars/car-01/claim")

    response = client.post("/api/cars/car-01/claim")
    assert response.status_code == 409


def test_heartbeat_unknown_car_returns_404(client):
    response = client.post("/api/cars/car-99/heartbeat")
    assert response.status_code == 404


def test_heartbeat_known_car_returns_204(client):
    register_car01(client)
    response = client.post("/api/cars/car-01/heartbeat")
    assert response.status_code == 204


def test_heartbeat_reports_active_session_and_protects_the_claim(client):
    register_car01(client)
    assert client.post("/api/cars/car-01/claim").status_code == 200

    # La voiture signale que la session vit toujours : la voiture reste
    # revendiquée, un second pilote ne peut pas la lui prendre.
    assert client.post("/api/cars/car-01/heartbeat", json={"session_active": True}).status_code == 204
    assert client.post("/api/cars/car-01/claim").status_code == 409


def test_heartbeat_reporting_no_session_releases_the_car(client):
    register_car01(client)
    assert client.post("/api/cars/car-01/claim").status_code == 200

    assert client.post("/api/cars/car-01/heartbeat", json={"session_active": False}).status_code == 204
    assert client.post("/api/cars/car-01/claim").status_code == 200


def test_heartbeat_without_body_is_still_accepted(client):
    register_car01(client)
    assert client.post("/api/cars/car-01/heartbeat").status_code == 204
