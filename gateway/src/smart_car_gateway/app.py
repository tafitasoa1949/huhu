"""Serveur Gateway — Phase 1 (docs/mobile-protocol.md).

Deux familles de routes :

- **publiques**, consommées par l'app mobile (`GatewayHttpAdapter.kt`) :
  `GET /api/cars`, `POST /api/cars/<car_id>/claim` — noms de champs JSON
  imposés côté fil, voir `GatewayDtos.kt`.
- **internes**, consommées uniquement par la voiture elle-même sur le même
  réseau local (`network/gateway_client.py` côté Raspberry Pi) :
  `POST /api/cars/register`, `POST /api/cars/<car_id>/heartbeat`. Pas
  d'authentification ici : le sujet suppose un réseau de TP de confiance,
  même hypothèse que le reste du protocole (le jeton protège la session de
  pilotage, pas ce canal d'administration).
"""

from __future__ import annotations

from flask import Flask, jsonify, request

from smart_car_gateway.http_claim import CarUnreachableError, claim_over_http
from smart_car_gateway.registry import CarAlreadyClaimedError, CarRegistry, CarUnknownError


def create_app(registry: CarRegistry | None = None) -> Flask:
    app = Flask(__name__)
    app.config["REGISTRY"] = registry or CarRegistry(claim_fn=claim_over_http)

    @app.get("/api/cars")
    def list_cars():
        reg: CarRegistry = app.config["REGISTRY"]
        return jsonify([
            {"car_id": car.car_id, "name": car.name, "online": online}
            for car, online in reg.list_cars()
        ])

    @app.post("/api/cars/<car_id>/claim")
    def claim_car(car_id: str):
        reg: CarRegistry = app.config["REGISTRY"]
        try:
            return jsonify(reg.claim(car_id))
        except CarUnknownError:
            return jsonify({"error": f"voiture inconnue ou hors ligne: {car_id}"}), 404
        except CarAlreadyClaimedError:
            return jsonify({"error": f"voiture déjà revendiquée: {car_id}"}), 409
        except CarUnreachableError as exc:
            return jsonify({"error": str(exc)}), 502

    @app.post("/api/cars/register")
    def register_car():
        reg: CarRegistry = app.config["REGISTRY"]
        body = request.get_json(force=True)
        reg.register(
            car_id=body["car_id"],
            name=body["name"],
            ip=body["ip"],
            control_port=body["control_port"],
            telemetry_port=body["telemetry_port"],
            video_port=body["video_port"],
            mgmt_port=body["mgmt_port"],
        )
        return "", 204

    @app.post("/api/cars/<car_id>/heartbeat")
    def heartbeat_car(car_id: str):
        reg: CarRegistry = app.config["REGISTRY"]
        # Corps facultatif : une voiture qui ne rapporte pas `session_active`
        # garde le comportement d'avant (voir `CarRegistry.heartbeat`).
        body = request.get_json(silent=True) or {}
        session_active = body.get("session_active")
        try:
            reg.heartbeat(car_id, session_active=session_active if isinstance(session_active, bool) else None)
        except CarUnknownError:
            return jsonify({"error": f"voiture inconnue: {car_id}"}), 404
        return "", 204

    return app
