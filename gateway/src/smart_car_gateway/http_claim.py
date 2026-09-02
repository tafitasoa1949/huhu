"""Implémentation réseau de `registry.ClaimFn` — appelle la voiture.

Séparé de `registry.py` pour que celui-ci reste testable sans réseau (un
faux `claim_fn` suffit dans les tests de `CarRegistry`).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from smart_car_gateway.registry import CarRecord


class CarUnreachableError(Exception):
    """La voiture n'a pas répondu à `/internal/claim` (HTTP 502 côté Gateway)."""


def claim_over_http(car: CarRecord, *, timeout_s: float = 3.0) -> tuple[str, int]:
    url = f"http://{car.ip}:{car.mgmt_port}/internal/claim"
    request = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise CarUnreachableError(f"{car.car_id} injoignable sur {url}: {exc}") from exc
    return body["token"], body["expires_in_s"]
