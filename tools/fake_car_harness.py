#!/usr/bin/env python3
"""Bac à sable de test manuel pour l'app mobile : simule Gateway + voiture.

Il n'existe encore ni Gateway (Phase 1) ni couche décision/réseau côté
Raspberry Pi (Phase 2) dans ce dépôt (docs/architecture.md, §État par
composant) — l'app mobile ne peut donc pas être essayée en conditions
réelles. Ce script fait tourner, sur un seul poste, de quoi dérouler l'écran
de connexion jusqu'à l'écran de conduite avec vidéo :

- ``GET /api/cars`` / ``POST /api/cars/{id}/claim`` (Phase 1, Gateway REST) ;
- un relais vidéo ``GET /stream`` (Phase 2, docs/mobile-protocol.md
  §Flux vidéo) — images de synthèse en BMP (pas de dépendance OpenCV/Pillow,
  ni de webcam requise), le nom de fichier/Content-Type ment sciemment
  (« image/jpeg ») car `MjpegVideoStreamAdapter` ne regarde que
  `Content-Length`, pas le type déclaré, et `BitmapFactory` décode d'après
  les octets réels, pas l'en-tête ;
- un flux de télémétrie TCP (Phase 2, §Télémétrie) ;
- une écoute UDP de contrôle (Phase 2, §Commandes) qui se contente
  d'afficher les paquets `drive`/`emergency` reçus, pour voir le joystick
  arriver en direct — sauf `mode` (AUTO/MANUAL), qui est mémorisé et
  aussitôt renvoyé dans le champ `mode` de la télémétrie, pour tester le
  bouton de bascule côté app sans vraie couche autonome.

Volontairement un jouet de test manuel, pas un simulateur fidèle : pas
d'arbitrage, pas de règles de sécurité, pas de watchdog. Pour ça, voir la
couche décision Raspberry Pi (à écrire, cf. docs/tasks.md).

Usage::

    python tools/fake_car_harness.py --ip 10.100.32.28

``--ip`` doit être l'adresse IP de ce poste sur le même Wi-Fi que le
téléphone (celle que l'app va effectivement contacter en Phase 2) ; sans
elle, le script tente de la deviner.
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CAR_ID = "car-01"
TOKEN = "test-token"


class SharedState:
    """Mode de conduite partagé entre les threads contrôle (écriture, sur
    réception d'un `mode` UDP) et télémétrie (lecture, à chaque trame) —
    tient lieu du bout d'arbitrage qu'une vraie couche décision Raspberry Pi
    ferait (docs/tasks.md, toujours à écrire)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mode = "MANUAL"

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode

    def get_mode(self) -> str:
        with self._lock:
            return self._mode


state = SharedState()


def guess_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# --- Vidéo de synthèse (BMP 24 bits, sans dépendance externe) ---------------

_PALETTE = [(30, 30, 200), (30, 160, 30), (200, 60, 30), (160, 30, 160)]


def make_bmp_frame(width: int, height: int, frame_index: int) -> bytes:
    """Image de test : fond qui change de couleur, carré blanc qui défile —
    juste de quoi voir à l'écran que le flux est bien vivant et à jour."""
    row_size = (width * 3 + 3) & ~3
    pad = row_size - width * 3

    bg = _PALETTE[(frame_index // 20) % len(_PALETTE)]
    bg_px = bytes((bg[2], bg[1], bg[0]))  # BMP stocke en BGR
    bg_row = bg_px * width + b"\x00" * pad

    square_w = max(10, width // 8)
    square_x = (frame_index * 3) % max(1, width - square_w)
    white_px = bytes((255, 255, 255))
    square_row = (
        bg_px * square_x + white_px * square_w + bg_px * (width - square_x - square_w) + b"\x00" * pad
    )

    band_top, band_bottom = height // 2 - 10, height // 2 + 10
    rows = bytearray()
    for y in range(height):
        rows += square_row if band_top <= y < band_bottom else bg_row

    pixel_data_size = row_size * height
    file_size = 54 + pixel_data_size
    file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
    info_header = struct.pack(
        "<IiiHHIIiiII", 40, width, height, 1, 24, 0, pixel_data_size, 2835, 2835, 0, 0
    )
    return file_header + info_header + bytes(rows)


# --- Serveur combiné : Gateway (Phase 1) + relais vidéo (Phase 2) ----------


def make_handler(car_ip: str, control_port: int, telemetry_port: int, video_port: int):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A002
            print(f"[harness] {self.address_string()} - {fmt % args}")

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/api/cars":
                self._json(200, [{"car_id": CAR_ID, "name": "Voiture de test", "online": True}])
            elif self.path.startswith("/stream"):
                self._stream_video()
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path == f"/api/cars/{CAR_ID}/claim":
                self._json(
                    200,
                    {
                        "car_id": CAR_ID,
                        "ip": car_ip,
                        "control_port": control_port,
                        "telemetry_port": telemetry_port,
                        "video_port": video_port,
                        "token": TOKEN,
                        "expires_in_s": 3600,
                    },
                )
            else:
                self.send_error(404)

        def _json(self, status: int, body) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _stream_video(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            frame_index = 0
            try:
                while True:
                    payload = make_bmp_frame(160, 120, frame_index)
                    header = (
                        f"Content-Type: image/jpeg\r\nContent-Length: {len(payload)}\r\n\r\n"
                    ).encode("ascii")
                    self.wfile.write(b"\r\n--frame\r\n")
                    self.wfile.write(header)
                    self.wfile.write(payload)
                    frame_index += 1
                    time.sleep(0.1)  # 10 fps, largement au-dessus du minimum 5 Hz du sujet
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass

    return Handler


def serve_gateway_and_video(car_ip: str, gateway_port: int, control_port: int, telemetry_port: int, video_port: int) -> None:
    handler = make_handler(car_ip, control_port, telemetry_port, video_port)
    server = ThreadingHTTPServer(("0.0.0.0", gateway_port), handler)
    print(f"[harness] Gateway  : http://{car_ip}:{gateway_port}/api/cars")
    print(f"[harness] Vidéo    : http://{car_ip}:{gateway_port}/stream (relayée aussi via video_port déclaré)")
    server.serve_forever()


# --- Télémétrie TCP (Phase 2, §Télémétrie) ----------------------------------


def serve_telemetry(port: int) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(1)
    print(f"[harness] Télémétrie TCP en écoute sur {port}")

    while True:
        conn, addr = server.accept()
        print(f"[harness] télémétrie : app connectée depuis {addr}")
        threading.Thread(target=_telemetry_loop, args=(conn,), daemon=True).start()


def _telemetry_loop(conn: socket.socket) -> None:
    seq = 0
    battery = 77
    try:
        with conn:
            while True:
                seq += 1
                battery = max(0, battery - (1 if seq % 50 == 0 else 0))
                frame = {
                    "type": "telemetry",
                    "seq": seq,
                    "ts_ms": int(time.time() * 1000),
                    "speed_pct": 0,
                    "steering_pct": 0,
                    "battery_pct": battery,
                    "rssi_dbm": -55,
                    "mode": state.get_mode(),
                }
                conn.sendall((json.dumps(frame) + "\n").encode("utf-8"))
                time.sleep(0.1)  # 10 Hz, au-dessus du minimum 5 Hz du sujet
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
        print("[harness] télémétrie : app déconnectée")


# --- Contrôle UDP (Phase 2, §Commandes) — affichage seul, pas d'arbitrage --


def serve_control(port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    print(f"[harness] Contrôle UDP en écoute sur {port} (affichage uniquement)")
    while True:
        data, addr = sock.recvfrom(4096)
        try:
            msg = json.loads(data.decode("utf-8"))
        except ValueError:
            continue
        if msg.get("type") == "drive":
            print(f"[harness] drive  v={msg.get('speed_pct'):>4} dir={msg.get('steering_pct'):>4}  (seq={msg.get('seq')})")
        elif msg.get("type") == "emergency":
            print("[harness] EMERGENCY reçu")
        elif msg.get("type") == "mode":
            mode = msg.get("mode")
            if mode in ("AUTO", "MANUAL"):
                state.set_mode(mode)
                print(f"[harness] mode -> {mode}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", default=None, help="IP de ce poste sur le Wi-Fi du téléphone (deviné si omis)")
    parser.add_argument("--gateway-port", type=int, default=8080)
    parser.add_argument("--control-port", type=int, default=5005)
    parser.add_argument("--telemetry-port", type=int, default=5006)
    parser.add_argument("--video-port", type=int, default=8080, help="même port que le Gateway ici : /stream y répond aussi")
    args = parser.parse_args()

    car_ip = args.ip or guess_local_ip()
    print(f"[harness] IP utilisée pour le claim : {car_ip}")
    print("[harness] Dans l'app : écran Connexion -> IP Gateway = "
          f"{car_ip}, port = {args.gateway_port}")

    threading.Thread(
        target=serve_gateway_and_video,
        args=(car_ip, args.gateway_port, args.control_port, args.telemetry_port, args.video_port),
        daemon=True,
    ).start()
    threading.Thread(target=serve_telemetry, args=(args.telemetry_port,), daemon=True).start()
    threading.Thread(target=serve_control, args=(args.control_port,), daemon=True).start()

    print("[harness] Prêt. Ctrl+C pour arrêter.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
