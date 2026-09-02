"""Teste le relais octet-pour-octet contre un faux ESP32-CAM local (même
esprit que `tools/fake_esp32cam_server.py`), tout en boucle locale — pas de
matériel ni de vrai réseau requis."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from smart_car.network.video_relay import create_server

FAKE_FRAME = (
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 4\r\n\r\nJPEG"
)


class _FakeCamHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=frame")
        self.end_headers()
        self.wfile.write(FAKE_FRAME)


@pytest.fixture
def fake_cam():
    server = HTTPServer(("127.0.0.1", 0), _FakeCamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/stream"
    server.shutdown()
    server.server_close()


@pytest.fixture
def relay(fake_cam):
    token = ["secret-token"]
    server = create_server(
        host="127.0.0.1", port=0, cam_stream_url=fake_cam, token_provider=lambda: token[0]
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, token
    server.shutdown()
    server.server_close()


def test_valid_token_relays_upstream_bytes_unchanged(relay):
    server, token = relay
    response = urllib.request.urlopen(
        f"http://127.0.0.1:{server.server_port}/stream?token={token[0]}", timeout=3.0
    )
    assert response.status == 200
    assert response.read() == FAKE_FRAME


def test_missing_token_rejected_with_403(relay):
    server, _token = relay
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/stream", timeout=3.0)
    assert exc_info.value.code == 403


def test_wrong_token_rejected_with_403(relay):
    server, _token = relay
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/stream?token=wrong", timeout=3.0
        )
    assert exc_info.value.code == 403


def test_expired_token_rejected_with_403(relay):
    server, token = relay
    valid_token = token[0]
    token[0] = None  # simule l'expiration côté token_provider

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/stream?token={valid_token}", timeout=3.0
        )
    assert exc_info.value.code == 403
