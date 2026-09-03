"""Serveur P2P — Phase 2 (docs/mobile-protocol.md) : canal de contrôle UDP
et télémétrie TCP. Le relais vidéo est un serveur HTTP séparé et synchrone
(`network/video_relay.py`) — une coupure vidéo ne doit jamais interférer
avec le watchdog de sécurité qui tourne ici.
"""

from __future__ import annotations

import asyncio
import json
import sys
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
    # `seq` est croissant "pour une session" (docs/mobile-protocol.md) : la
    # session, c'est le jeton actif, pas la durée de vie du process. Sans
    # `token` ici pour détecter le changement, `last_seq` ne redescendrait
    # jamais entre deux claims, et toute reconnexion (l'app recommence à 1)
    # se ferait rejeter indéfiniment comme "périmée".
    token: str | None = None
    last_seq: int = -1
    last_valid_packet_monotonic: float | None = None
    applied_speed_pct: int = 0
    applied_steering_pct: int = 0
    mode: str = "MANUAL"
    telemetry_seq: int = 0
    # Dernier paquet `drive` : horloge du téléphone (`ts_ms`) et horloge de la
    # voiture (`self._clock()`) au moment de la réception, l'une en face de
    # l'autre. Sert à mesurer un retard *relatif* d'un paquet au suivant
    # (docs/mobile-protocol.md, §fraîcheur) sans jamais comparer `ts_ms` à
    # l'horloge de la voiture en absolu — les deux horloges n'ont aucune
    # raison d'être synchronisées (voir `_handle_drive`).
    last_drive_ts_ms: int | None = None
    last_drive_recv_monotonic: float | None = None


class _ControlProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: "P2pServer") -> None:
        self._server = server

    def datagram_received(self, data: bytes, addr) -> None:
        self._server._handle_control_packet(data, addr)


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
        # Diagnostic uniquement : un paquet UDP invalide est silencieux par
        # design (docs/mobile-protocol.md — pas d'accusé de réception sur ce
        # canal), donc sans ce log il est impossible de distinguer "rien
        # n'arrive" de "ça arrive mais c'est rejeté". Limité à 1 ligne/s par
        # cause pour ne pas noyer la sortie à 20 Hz.
        self._last_reject_log: dict[str, float] = {}
        self._last_accept_log = float("-inf")
        self._last_watchdog_log = float("-inf")

    def _log_rejected(self, reason: str, packet: object = None) -> None:
        now = self._clock()
        last = self._last_reject_log.get(reason, float("-inf"))
        if now - last < 1.0:
            return
        self._last_reject_log[reason] = now
        print(f"[p2p_server] paquet UDP rejeté ({reason}): {packet!r}", file=sys.stderr)

    def _log_accepted(self, addr, packet_type: str, seq: int, packet: dict) -> None:
        """Pendant de [_log_rejected], sans quoi le journal ne répond pas à la
        seule question qu'on lui pose en test manuel : « est-ce que la
        commande du téléphone arrive ? ». Un paquet accepté joystick au
        centre et le watchdog qui force l'arrêt produisent en effet la même
        ligne moteur (`speed=+0%`), à la même cadence (20 Hz)."""
        now = self._clock()
        if now - self._last_accept_log < 1.0:
            return
        self._last_accept_log = now
        source = f"{addr[0]}:{addr[1]}" if addr else "source inconnue"
        detail = ""
        if packet_type == "drive":
            detail = f" speed={packet.get('speed_pct')}% steering={packet.get('steering_pct')}%"
        elif packet_type == "mode":
            detail = f" mode={packet.get('mode')}"
        print(
            f"[p2p_server] paquet accepté de {source}: {packet_type} seq={seq}{detail}",
            file=sys.stderr,
        )

    def _log_watchdog_stop(self, reason: str, ms_since: float) -> None:
        now = self._clock()
        if now - self._last_watchdog_log < 1.0:
            return
        self._last_watchdog_log = now
        since = "aucun depuis le démarrage" if ms_since == float("inf") else f"il y a {int(ms_since)} ms"
        print(
            f"[p2p_server] watchdog: arrêt forcé ({reason}) — dernier paquet valide: {since}",
            file=sys.stderr,
        )

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

    def _handle_control_packet(self, data: bytes, addr: tuple[str, int] | None = None) -> None:
        try:
            packet = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._log_rejected("JSON invalide", data)
            return
        if not isinstance(packet, dict):
            self._log_rejected("pas un objet JSON", packet)
            return

        expected_token = self._token_provider()
        if expected_token is None:
            self._log_rejected("aucun jeton actif côté voiture")
            return
        if packet.get("token") != expected_token:
            self._log_rejected("jeton invalide/expiré", packet.get("token"))
            return

        # Nouveau jeton actif depuis le dernier paquet traité = nouvelle
        # session (nouveau claim, app relancée...) : la numérotation de
        # l'app est repartie de 1 côté client, la nôtre doit en faire autant
        # plutôt que de comparer contre un `last_seq` hérité d'une session
        # précédente qui n'a aucun rapport.
        if expected_token != self._session.token:
            self._session.token = expected_token
            self._session.last_seq = -1
            self._session.last_drive_ts_ms = None
            self._session.last_drive_recv_monotonic = None

        seq = packet.get("seq")
        if not isinstance(seq, int) or seq <= self._session.last_seq:
            self._log_rejected(f"seq non croissant (reçu={seq}, dernier={self._session.last_seq})")
            return

        packet_type = packet.get("type")
        if packet_type not in ("drive", "emergency", "mode"):
            self._log_rejected("type inconnu", packet_type)
            return

        self._session.last_seq = seq
        self._on_valid_packet()
        self._log_accepted(addr, packet_type, seq, packet)

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
        if isinstance(ts_ms, int):
            now_monotonic = self._clock()
            last_ts_ms = self._session.last_drive_ts_ms
            last_recv_monotonic = self._session.last_drive_recv_monotonic
            if last_ts_ms is not None and last_recv_monotonic is not None:
                # Régression corrigée ici : ce calcul comparait auparavant
                # `ts_ms` (horloge du téléphone) à l'horloge de la voiture en
                # absolu — exactement ce que docs/mobile-protocol.md interdit
                # (« jamais comparé à l'horloge de la voiture »), parce que
                # rien ne garantit que les deux horloges sont synchronisées.
                # Sur ce banc, un écart constant d'environ 200-260 ms entre
                # les deux faisait rejeter la quasi-totalité des paquets
                # comme "périmés", alors qu'aucun retard réseau réel
                # n'existait — silencieusement, avant l'ajout du journal
                # ci-dessous : le joystick semblait ne "rien faire".
                #
                # Un décalage d'horloge *constant* n'affecte jamais ce
                # calcul-ci : seul un paquet qui a mis plus de temps à
                # arriver que ce que le téléphone pensait avoir laissé
                # s'écouler (retard réseau/ordonnancement réel) déclenche le
                # rejet.
                phone_elapsed_ms = ts_ms - last_ts_ms
                car_elapsed_ms = (now_monotonic - last_recv_monotonic) * 1000
                network_delay_ms = car_elapsed_ms - phone_elapsed_ms
                if network_delay_ms > DRIVE_STALE_MS:
                    # Paquet valide (token/seq ok, donc a bien nourri le
                    # watchdog ci-dessus) mais arrivé avec trop de retard :
                    # on ne rejoue pas une commande périmée, on attend la
                    # suivante. Journalisé séparément de `_log_accepted` :
                    # sans ça, un paquet "accepté" au sens token/séquence
                    # peut quand même ne jamais atteindre le moteur, sans
                    # rien qui le distingue d'un paquet réellement appliqué.
                    self._log_rejected(
                        f"drive périmé (retard réseau ~{network_delay_ms:.0f}ms, seuil {DRIVE_STALE_MS}ms)"
                    )
                    return
            self._session.last_drive_ts_ms = ts_ms
            self._session.last_drive_recv_monotonic = now_monotonic

        speed_pct = packet.get("speed_pct")
        steering_pct = packet.get("steering_pct")
        if not isinstance(speed_pct, int) or not isinstance(steering_pct, int):
            self._log_rejected("speed_pct/steering_pct absents ou non entiers", packet)
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
                self._log_watchdog_stop(decision.stopped_reason, ms_since)

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
