"""État en mémoire du Gateway — Phase 1 (docs/mobile-protocol.md).

Le Gateway ne fabrique jamais lui-même le jeton de session : il relaie un
appel à la voiture (`claim_fn`), seule source de vérité sur ce qu'elle
acceptera ensuite en Phase 2. `CarRegistry` ne sait rien de HTTP — c'est
`app.py` qui l'expose en Flask et qui fournit un `claim_fn` réel ; les tests
en injectent un faux.

Volontairement sans persistance : un redémarrage du Gateway force chaque
voiture à se réenregistrer via son heartbeat, il n'y a donc jamais d'état
périmé à réconcilier au redémarrage.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

HEARTBEAT_TIMEOUT_S = 10.0


class CarUnknownError(Exception):
    """La voiture n'est pas enregistrée, ou son heartbeat a expiré."""


class CarAlreadyClaimedError(Exception):
    """La voiture est déjà revendiquée par un autre pilote (HTTP 409)."""


@dataclass
class CarRecord:
    car_id: str
    name: str
    ip: str
    control_port: int
    telemetry_port: int
    video_port: int
    mgmt_port: int
    last_heartbeat_ts: float
    claimed_until_ts: float | None = None

    def is_online(self, now: float) -> bool:
        return now - self.last_heartbeat_ts <= HEARTBEAT_TIMEOUT_S

    def is_claimed(self, now: float) -> bool:
        return self.claimed_until_ts is not None and now < self.claimed_until_ts


ClaimFn = Callable[[CarRecord], tuple[str, int]]
"""Appelle la voiture pour obtenir (token, expires_in_s). Lève sur échec réseau."""


class CarRegistry:
    def __init__(self, *, claim_fn: ClaimFn, clock: Callable[[], float] = time.monotonic) -> None:
        self._cars: dict[str, CarRecord] = {}
        self._claim_fn = claim_fn
        self._clock = clock

    def register(
        self,
        *,
        car_id: str,
        name: str,
        ip: str,
        control_port: int,
        telemetry_port: int,
        video_port: int,
        mgmt_port: int,
    ) -> None:
        # Un ré-enregistrement (redémarrage de la voiture, IP DHCP qui a
        # changé) ne doit pas effacer un claim en cours — sinon un pilote en
        # pleine session perdrait sa revendication à cause d'un heartbeat qui
        # a raté une fenêtre.
        existing = self._cars.get(car_id)
        self._cars[car_id] = CarRecord(
            car_id=car_id,
            name=name,
            ip=ip,
            control_port=control_port,
            telemetry_port=telemetry_port,
            video_port=video_port,
            mgmt_port=mgmt_port,
            last_heartbeat_ts=self._clock(),
            claimed_until_ts=existing.claimed_until_ts if existing else None,
        )

    def heartbeat(self, car_id: str, *, session_active: bool | None = None) -> None:
        """`session_active` : ce que la voiture rapporte de sa session en cours.

        La voiture est seule à savoir si un pilote roule encore — son jeton se
        prolonge à chaque paquet valide (docs/mobile-protocol.md : « valable
        [...] s'il n'y a pas de trafic »), pas le Gateway. Sans ce recalage, la
        fenêtre posée au claim (`expires_in_s`) expirait au bout de 30 s alors
        que la session vivait toujours : le claim suivant était accepté, la
        voiture émettait un nouveau jeton, et toutes les commandes du pilote en
        cours se faisaient rejeter en silence (l'app continuait d'afficher
        « lié », la télémétrie n'étant pas concernée).

        `None` = la voiture ne rapporte pas ce champ : on ne touche pas à la
        revendication, exactement comme avant.
        """
        car = self._cars.get(car_id)
        if car is None:
            raise CarUnknownError(car_id)
        now = self._clock()
        car.last_heartbeat_ts = now
        if session_active is True:
            car.claimed_until_ts = now + HEARTBEAT_TIMEOUT_S
        elif session_active is False:
            # Plus de session côté voiture : elle redevient libre tout de
            # suite, plutôt que de rester revendiquée jusqu'au bout d'une
            # fenêtre qui ne correspond plus à rien (c'est ce qui imposait
            # d'attendre 30 s avant de pouvoir se reconnecter).
            car.claimed_until_ts = None

    def list_cars(self) -> list[tuple[CarRecord, bool]]:
        """Renvoie chaque voiture connue avec son statut `online` calculé."""
        now = self._clock()
        return [(car, car.is_online(now)) for car in self._cars.values()]

    def claim(self, car_id: str) -> dict:
        now = self._clock()
        car = self._cars.get(car_id)
        if car is None or not car.is_online(now):
            raise CarUnknownError(car_id)
        if car.is_claimed(now):
            raise CarAlreadyClaimedError(car_id)

        # La voiture peut refuser (matériel non prêt, etc.) : dans ce cas
        # `claim_fn` lève, et on ne marque surtout pas la voiture comme
        # revendiquée pour un jeton qui n'existe pas côté voiture.
        token, expires_in_s = self._claim_fn(car)

        car.claimed_until_ts = now + expires_in_s
        return {
            "car_id": car.car_id,
            "ip": car.ip,
            "control_port": car.control_port,
            "telemetry_port": car.telemetry_port,
            "video_port": car.video_port,
            "token": token,
            "expires_in_s": expires_in_s,
        }
