"""Serveur P2P — Phase 2 (docs/mobile-protocol.md) : canal de contrôle UDP
et télémétrie TCP. Le relais vidéo est un serveur HTTP séparé et synchrone
(`network/video_relay.py`) — une coupure vidéo ne doit jamais interférer
avec le watchdog de sécurité qui tourne ici.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Callable

from smart_car.motors import safety
from smart_car.motors.driver import MotorDriver

# ts_ms trop vieux -> paquet drive ignoré (docs/mobile-protocol.md).
DRIVE_STALE_MS = 150
# Télémétrie : au moins 5 mises à jour par seconde (docs/architecture.md, NFR).
TELEMETRY_INTERVAL_S = 1 / 5
WATCHDOG_TICK_S = 0.05


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class _SessionState:
    last_seq: int = -1
    last_valid_packet_monotonic: float | None = None
    applied_speed_pct: int = 0
    applied_steering_pct: int = 0
    mode: str = "MANUAL"
    telemetry_seq: int = 0


class _ControlProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: "P2pServer") -> None:
        self._server = server

    def datagram_received(self, data: bytes, addr) -> None:
        self._server._handle_control_packet(data)


class P2pServer:
    def __init__(
        self,
        *,
        driver: MotorDriver,
        control_port: int,
        telemetry_port: int,
        token_provider: Callable[[], str | None],
        on_valid_packet: Callable[[], None] = lambda: None,
        physical_estop: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._driver = driver
        self._control_port = control_port
        self._telemetry_port = telemetry_port
        self._token_provider = token_provider
        self._on_valid_packet = on_valid_packet
        self._physical_estop = physical_estop
        self._clock = clock

        self._session = _SessionState()
        self._telemetry_clients: list[asyncio.StreamWriter] = []
        self._transport: asyncio.DatagramTransport | None = None
        self._telemetry_server: asyncio.base_events.Server | None = None
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _ControlProtocol(self), local_addr=("0.0.0.0", self._control_port)
        )
        self._telemetry_server = await asyncio.start_server(
            self._handle_telemetry_client, "0.0.0.0", self._telemetry_port
        )
        self._tasks.append(asyncio.create_task(self._watchdog_loop()))
        self._tasks.append(asyncio.create_task(self._telemetry_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._transport is not None:
            self._transport.close()
        if self._telemetry_server is not None:
            self._telemetry_server.close()
            await self._telemetry_server.wait_closed()

    @property
    def applied_speed_pct(self) -> int:
        return self._session.applied_speed_pct

    @property
    def applied_steering_pct(self) -> int:
        return self._session.applied_steering_pct

    # ------------------------------------------------------------------
    # Contrôle — UDP, app -> voiture
    # ------------------------------------------------------------------

    def _handle_control_packet(self, data: bytes) -> None:
        try:
            packet = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(packet, dict):
            return

        expected_token = self._token_provider()
        if expected_token is None or packet.get("token") != expected_token:
            return

        seq = packet.get("seq")
        if not isinstance(seq, int) or seq <= self._session.last_seq:
            return

        packet_type = packet.get("type")
        if packet_type not in ("drive", "emergency", "mode"):
            return

        self._session.last_seq = seq
        self._on_valid_packet()

        # `mode` n'est envoyé qu'une fois au clic, pas à 20 Hz : il ne doit
        # pas faire vivre le watchdog de liaison à sa place
        # (docs/mobile-protocol.md : « drive/emergency/heartbeat »).
        if packet_type in ("drive", "emergency"):
            self._session.last_valid_packet_monotonic = self._clock()

        if packet_type == "mode":
            self._handle_mode(packet)
        elif packet_type == "emergency":
            self._handle_emergency()
        else:
            self._handle_drive(packet)

    def _handle_mode(self, packet: dict) -> None:
        # Pas de boucle de décision autonome dans ce dépôt pour l'instant
        # (docs/architecture.md) : AUTO est accepté et renvoyé tel quel en
        # télémétrie, mais ne déclenche aucun comportement différent ici.
        requested_mode = packet.get("mode")
        if requested_mode in ("AUTO", "MANUAL"):
            self._session.mode = requested_mode

    def _handle_emergency(self) -> None:
        decision = safety.decide(
            requested_speed_pct=0,
            requested_steering_pct=0,
            emergency=True,
            physical_estop_engaged=self._physical_estop(),
            ms_since_last_valid_packet=0,
        )
        self._apply_decision(decision)

    def _handle_drive(self, packet: dict) -> None:
        ts_ms = packet.get("ts_ms")
        if isinstance(ts_ms, int) and _now_ms() - ts_ms > DRIVE_STALE_MS:
            # Paquet valide (token/seq ok, donc a bien nourri le watchdog
            # ci-dessus) mais périmé : on ne rejoue pas une commande en
            # retard, on attend la suivante.
            return

        speed_pct = packet.get("speed_pct")
        steering_pct = packet.get("steering_pct")
        if not isinstance(speed_pct, int) or not isinstance(steering_pct, int):
            return

        decision = safety.decide(
            requested_speed_pct=speed_pct,
            requested_steering_pct=steering_pct,
            emergency=False,
            physical_estop_engaged=self._physical_estop(),
            ms_since_last_valid_packet=0,
        )
        self._apply_decision(decision)

    def _apply_decision(self, decision: safety.DriveDecision) -> None:
        self._session.applied_speed_pct = decision.speed_pct
        self._session.applied_steering_pct = decision.steering_pct
        self._driver.apply(decision.speed_pct, decision.steering_pct)

    # ------------------------------------------------------------------
    # Watchdog — indépendant du flux de paquets, détecte le silence
    # ------------------------------------------------------------------

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(WATCHDOG_TICK_S)
            last = self._session.last_valid_packet_monotonic
            ms_since = (self._clock() - last) * 1000 if last is not None else float("inf")
            decision = safety.decide(
                requested_speed_pct=self._session.applied_speed_pct,
                requested_steering_pct=self._session.applied_steering_pct,
                emergency=False,
                physical_estop_engaged=self._physical_estop(),
                ms_since_last_valid_packet=ms_since,
            )
            if decision.stopped_reason is not None:
                self._apply_decision(decision)

    # ------------------------------------------------------------------
    # Télémétrie — TCP, voiture -> app
    # ------------------------------------------------------------------

    async def _handle_telemetry_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._telemetry_clients.append(writer)
        try:
            await reader.read()  # le client n'envoie rien ; sert juste à détecter la déconnexion
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        finally:
            if writer in self._telemetry_clients:
                self._telemetry_clients.remove(writer)
            # `eof_received()` du protocole stream renvoie `True` (le sens
            # écriture reste ouvert pour la boucle de télémétrie) : sans ce
            # `close()` explicite, la connexion resterait comptée comme
            # active par le `Server` asyncio et `wait_closed()` ne
            # reviendrait jamais.
            writer.close()

    async def _telemetry_loop(self) -> None:
        while True:
            await asyncio.sleep(TELEMETRY_INTERVAL_S)
            self._session.telemetry_seq += 1
            frame = {
                "type": "telemetry",
                "seq": self._session.telemetry_seq,
                "ts_ms": _now_ms(),
                "speed_pct": self._session.applied_speed_pct,
                "steering_pct": self._session.applied_steering_pct,
                # null tant qu'aucun capteur n'est câblé — jamais 0
                # (docs/mobile-protocol.md, même convention que docs/contracts.md).
                "battery_pct": None,
                "rssi_dbm": None,
                "mode": self._session.mode,
            }
            line = (json.dumps(frame) + "\n").encode("utf-8")
            stale_writers = []
            for writer in self._telemetry_clients:
                try:
                    writer.write(line)
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError):
                    stale_writers.append(writer)
            for writer in stale_writers:
                self._telemetry_clients.remove(writer)
