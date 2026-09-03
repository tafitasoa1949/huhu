"""Teste le serveur P2P de bout en bout au niveau réseau (vrais sockets
UDP/TCP en boucle locale, horloge injectée pour le watchdog) — contre les
mêmes noms de champs JSON que `P2pDtos.kt` côté app (docs/mobile-protocol.md)."""

from __future__ import annotations

import asyncio
import itertools
import json
import socket
import time

import pytest

from smart_car.motors.driver import MotorDriver
from smart_car.network.p2p_server import P2pServer

_port_counter = itertools.count(15100, step=2)


def _wire_now_ms() -> int:
    return int(time.time() * 1000)


class RecordingDriver(MotorDriver):
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def apply(self, speed_pct: int, steering_pct: int) -> None:
        self.calls.append((speed_pct, steering_pct))

    def stop(self) -> None:
        self.apply(0, 0)


def send_udp(port: int, payload: dict) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(json.dumps(payload).encode("utf-8"), ("127.0.0.1", port))
    finally:
        sock.close()


@pytest.fixture
async def running_server():
    control_port = next(_port_counter)
    telemetry_port = next(_port_counter)
    driver = RecordingDriver()
    now = [0.0]
    touched = [0]
    server = P2pServer(
        driver=driver,
        control_port=control_port,
        telemetry_port=telemetry_port,
        token_provider=lambda: "tok-123",
        on_valid_packet=lambda: touched.__setitem__(0, touched[0] + 1),
        clock=lambda: now[0],
    )
    await server.start()
    try:
        yield server, driver, control_port, telemetry_port, now, touched
    finally:
        await server.stop()


async def test_valid_drive_packet_is_applied(running_server):
    _server, driver, control_port, _telemetry_port, _now, _touched = running_server

    send_udp(
        control_port,
        {"type": "drive", "token": "tok-123", "seq": 1, "ts_ms": _wire_now_ms(), "speed_pct": 40, "steering_pct": -10},
    )
    await asyncio.sleep(0.05)

    assert driver.calls[-1] == (40, -10)


async def test_out_of_range_values_are_clamped(running_server):
    _server, driver, control_port, _telemetry_port, _now, _touched = running_server

    send_udp(
        control_port,
        {"type": "drive", "token": "tok-123", "seq": 1, "ts_ms": _wire_now_ms(), "speed_pct": 500, "steering_pct": -500},
    )
    await asyncio.sleep(0.05)

    assert driver.calls[-1] == (100, -100)


async def test_wrong_token_is_ignored(running_server):
    _server, driver, control_port, _telemetry_port, _now, _touched = running_server

    send_udp(
        control_port,
        {"type": "drive", "token": "wrong", "seq": 1, "ts_ms": _wire_now_ms(), "speed_pct": 40, "steering_pct": 0},
    )
    await asyncio.sleep(0.02)

    # Aucun paquet valide reçu -> le watchdog applique déjà (0, 0) de
    # lui-même (aucune commande depuis le démarrage) ; ce qui compte ici,
    # c'est que le paquet au mauvais jeton n'ait jamais été appliqué.
    assert (40, 0) not in driver.calls


async def test_stale_sequence_is_ignored(running_server):
    _server, driver, control_port, _telemetry_port, _now, _touched = running_server

    send_udp(control_port, {"type": "drive", "token": "tok-123", "seq": 5, "ts_ms": _wire_now_ms(), "speed_pct": 10, "steering_pct": 0})
    await asyncio.sleep(0.05)
    send_udp(control_port, {"type": "drive", "token": "tok-123", "seq": 5, "ts_ms": _wire_now_ms(), "speed_pct": 99, "steering_pct": 0})
    await asyncio.sleep(0.05)

    # Le second paquet (seq égal, pas strictement croissant) doit être
    # ignoré : la dernière commande appliquée reste celle du premier.
    assert driver.calls[-1] == (10, 0)


async def test_drive_packet_delayed_relative_to_phone_clock_is_not_applied(running_server):
    # La fraîcheur se mesure au *retard* d'un paquet par rapport au suivant
    # (docs/mobile-protocol.md), jamais en comparant `ts_ms` à l'horloge de
    # la voiture en absolu — voir `test_constant_clock_offset...` ci-dessous
    # pour la régression que ça corrige.
    _server, driver, control_port, _telemetry_port, now, touched = running_server

    # Premier paquet : rien à comparer encore, toujours appliqué.
    send_udp(control_port, {"type": "drive", "token": "tok-123", "seq": 1, "ts_ms": 1000, "speed_pct": 10, "steering_pct": 0})
    await asyncio.sleep(0.05)
    assert driver.calls[-1] == (10, 0)

    # Le téléphone pense que 20 ms se sont écoulées ; côté voiture, l'horloge
    # injectée avance de 480 ms avant que ce paquet soit traité — un vrai
    # retard réseau/ordonnancement de 460 ms, bien au-dessus du seuil (150 ms).
    now[0] = 0.5
    send_udp(control_port, {"type": "drive", "token": "tok-123", "seq": 2, "ts_ms": 1020, "speed_pct": 70, "steering_pct": 0})
    await asyncio.sleep(0.05)

    assert driver.calls[-1] == (10, 0)  # pas rejoué : la commande précédente tient
    assert (70, 0) not in driver.calls
    # Mais le paquet a quand même compté pour le watchdog (token/seq valides).
    assert touched[0] == 2


async def test_constant_clock_offset_between_phone_and_car_never_causes_rejection(running_server):
    # Régression : ce calcul comparait auparavant `ts_ms` (horloge du
    # téléphone) à l'horloge de la voiture en absolu. Un simple décalage
    # constant entre les deux (aucune synchronisation garantie entre un
    # téléphone et un Raspberry Pi) suffisait à faire rejeter quasiment
    # tous les paquets comme "périmés" — observé au banc : ~200-260 ms
    # d'écart, joystick silencieusement inopérant.
    _server, driver, control_port, _telemetry_port, now, _touched = running_server

    # Horloge du téléphone très en avance sur celle de la voiture (10
    # minutes) : un décalage constant énorme, jamais un vrai retard réseau.
    phone_clock_offset_ms = 600_000
    for seq, (speed_pct, elapsed_s) in enumerate(
        [(10, 0.0), (20, 0.05), (30, 0.05), (40, 0.05)], start=1
    ):
        now[0] += elapsed_s
        ts_ms = phone_clock_offset_ms + int(now[0] * 1000)
        send_udp(
            control_port,
            {"type": "drive", "token": "tok-123", "seq": seq, "ts_ms": ts_ms, "speed_pct": speed_pct, "steering_pct": 0},
        )
        await asyncio.sleep(0.05)

    assert driver.calls[-1] == (40, 0)


async def test_emergency_forces_immediate_stop(running_server):
    _server, driver, control_port, _telemetry_port, _now, _touched = running_server

    send_udp(control_port, {"type": "drive", "token": "tok-123", "seq": 1, "ts_ms": _wire_now_ms(), "speed_pct": 80, "steering_pct": 20})
    await asyncio.sleep(0.05)
    send_udp(control_port, {"type": "emergency", "token": "tok-123", "seq": 2, "ts_ms": _wire_now_ms()})
    await asyncio.sleep(0.05)

    assert driver.calls[-1] == (0, 0)


async def test_watchdog_stops_after_silence_past_control_timeout(running_server):
    _server, driver, control_port, _telemetry_port, now, _touched = running_server

    send_udp(control_port, {"type": "drive", "token": "tok-123", "seq": 1, "ts_ms": _wire_now_ms(), "speed_pct": 50, "steering_pct": 0})
    await asyncio.sleep(0.05)
    assert driver.calls[-1] == (50, 0)

    now[0] = 3.0  # > 2000 ms depuis le dernier paquet valide (clock injectée)
    await asyncio.sleep(0.15)  # laisse quelques ticks au watchdog (50 ms/tick)

    assert driver.calls[-1] == (0, 0)


async def test_new_token_resets_sequence_tracking():
    # Reproduit le bug observé en test manuel : l'app repart de seq=1 à
    # chaque nouveau claim (nouveau jeton), mais le serveur ne doit pas
    # comparer ça au `last_seq` d'une session précédente, sans quoi toute
    # reconnexion se retrouve rejetée en permanence comme "périmée".
    control_port = next(_port_counter)
    telemetry_port = next(_port_counter)
    driver = RecordingDriver()
    token = ["tok-session-1"]
    server = P2pServer(
        driver=driver,
        control_port=control_port,
        telemetry_port=telemetry_port,
        token_provider=lambda: token[0],
    )
    await server.start()
    try:
        # Première session : seq 1..3, comme une app qui vient de se connecter.
        for seq in (1, 2, 3):
            send_udp(
                control_port,
                {"type": "drive", "token": token[0], "seq": seq, "ts_ms": _wire_now_ms(), "speed_pct": 10, "steering_pct": 0},
            )
            await asyncio.sleep(0.02)
        assert driver.calls[-1] == (10, 0)

        # Nouveau claim : nouveau jeton, l'app côté Kotlin repart de seq=1
        # (SequenceCounter est réinitialisé à chaque nouvelle CarPilotSession).
        token[0] = "tok-session-2"
        send_udp(
            control_port,
            {"type": "drive", "token": token[0], "seq": 1, "ts_ms": _wire_now_ms(), "speed_pct": 77, "steering_pct": -20},
        )
        await asyncio.sleep(0.05)

        # Sans le correctif, ce paquet serait rejeté (1 <= 3) et la dernière
        # commande appliquée resterait celle de l'ancienne session.
        assert driver.calls[-1] == (77, -20)
    finally:
        await server.stop()


async def test_telemetry_client_receives_json_lines(running_server):
    _server, driver, control_port, telemetry_port, _now, _touched = running_server

    send_udp(control_port, {"type": "drive", "token": "tok-123", "seq": 1, "ts_ms": _wire_now_ms(), "speed_pct": 33, "steering_pct": -7})
    await asyncio.sleep(0.05)

    reader, writer = await asyncio.open_connection("127.0.0.1", telemetry_port)
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=1.0)
        frame = json.loads(line)
        assert frame["type"] == "telemetry"
        assert frame["speed_pct"] == 33
        assert frame["steering_pct"] == -7
        assert frame["battery_pct"] is None
        assert frame["rssi_dbm"] is None
        assert frame["mode"] == "MANUAL"
    finally:
        writer.close()
        await writer.wait_closed()
