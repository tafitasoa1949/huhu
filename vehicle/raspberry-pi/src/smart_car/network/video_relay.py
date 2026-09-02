"""Relais vidéo — HTTP, voiture -> app (docs/mobile-protocol.md, §Flux vidéo).

Reproxifie **octet pour octet** le flux `multipart/x-mixed-replace` de
l'ESP32-CAM vers chaque client connecté, sans décoder ni réencoder — c'est
la décision actée dans docs/architecture.md (le Pi 5 n'a pas d'encodeur
matériel, réencoder coûterait du CPU logiciel pour rien). Contrairement à
`vision/mjpeg_source.py`, ce module ne regarde jamais le contenu des images.

Implémentation volontairement synchrone (`ThreadingHTTPServer`), même style
que `tools/fake_esp32cam_server.py` : chaque client vidéo occupe un fil
dédié à copier des octets, sans jamais toucher à la boucle asyncio du
contrôle/télémétrie (`network/p2p_server.py`), qui doit rester réactive pour
le watchdog de sécurité.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

CHUNK_SIZE = 4096
DEFAULT_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame"


def _make_handler(cam_stream_url: str, token_provider: Callable[[], str | None]):
    class VideoRelayHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            sys.stderr.write(f"[video_relay] {self.address_string()} - {format % args}\n")

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/stream":
                self.send_error(404)
                return

            query_token = parse_qs(parsed.query).get("token", [None])[0]
            expected_token = token_provider()
            # Jeton absent, inconnu ou expiré : rejeté, même règle que les
            # canaux UDP/TCP (docs/mobile-protocol.md, §Flux vidéo).
            if expected_token is None or query_token != expected_token:
                self.send_error(403, "jeton absent, inconnu ou expiré")
                return

            try:
                upstream = urllib.request.urlopen(cam_stream_url, timeout=5.0)
            except (urllib.error.URLError, TimeoutError) as exc:
                self.send_error(502, f"ESP32-CAM injoignable: {exc}")
                return

            self.send_response(200)
            self.send_header(
                "Content-Type", upstream.headers.get("Content-Type", DEFAULT_CONTENT_TYPE)
            )
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            try:
                while True:
                    chunk = upstream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # Client déconnecté : fin normale, même choix que
                # tools/fake_esp32cam_server.py.
                pass
            finally:
                upstream.close()

    return VideoRelayHandler


def create_server(
    *, host: str, port: int, cam_stream_url: str, token_provider: Callable[[], str | None]
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), _make_handler(cam_stream_url, token_provider))
