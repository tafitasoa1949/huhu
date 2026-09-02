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


async def test_drive_packet_older_than_150ms_is_not_applied(running_server):
    _server, driver, control_port, _telemetry_port, _now, touched = running_server

    old_ts = _wire_now_ms() - 500
    send_udp(control_port, {"type": "drive", "token": "tok-123", "seq": 1, "ts_ms": old_ts, "speed_pct": 70, "steering_pct": 0})
    await asyncio.sleep(0.05)

    assert driver.calls == []
    # Mais le paquet a quand même compté pour le watchdog (token/seq valides).
    assert touched[0] == 1


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
