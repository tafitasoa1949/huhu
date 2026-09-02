"""Tests de `smart_car.vision.mjpeg_source`, sans matériel ni webcam.

Le serveur utilisé ici est un jouet minimal — pas `tools/fake_esp32cam_server.py`,
qui a besoin d'une webcam réelle — mais il rejoue des JPEG déjà encodés avec
exactement le même format multipart que le firmware (voir
`esp32-cam/src/main.cpp`), pour tester le client dans les mêmes conditions.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import cv2
import numpy as np

from smart_car.vision.mjpeg_source import MjpegFrameSource

_BOUNDARY = b"\r\n--frame\r\n"


def _encode(color: tuple[int, int, int]) -> bytes:
    frame = np.full((16, 16, 3), color, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


class _ToyMjpegServer:
    """Rejoue une liste de JPEG en boucle, sur un port local libre."""

    def __init__(self, jpegs: list[bytes]) -> None:
        payloads = jpegs

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass  # silence : un test ne doit pas noyer la console

            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header(
                    "Content-Type", "multipart/x-mixed-replace;boundary=frame"
                )
                self.end_headers()
                try:
                    while True:
                        for payload in payloads:
                            header = (
                                f"Content-Type: image/jpeg\r\n"
                                f"Content-Length: {len(payload)}\r\n\r\n"
                            ).encode("ascii")
                            self.wfile.write(_BOUNDARY)
                            self.wfile.write(header)
                            self.wfile.write(payload)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        _, port = self._server.server_address
        return f"http://127.0.0.1:{port}/stream"

    def __enter__(self) -> "_ToyMjpegServer":
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.shutdown()
        self._server.server_close()


def test_reads_decoded_frames_matching_source_colors() -> None:
    jpegs = [_encode((10, 20, 30)), _encode((200, 100, 50))]
    with _ToyMjpegServer(jpegs) as server:
        with MjpegFrameSource(server.url) as source:
            first = source.read()
            second = source.read()

    assert first is not None
    assert second is not None
    assert first.shape == (16, 16, 3)
    # Une image ré-encodée en JPEG n'est jamais pixel-parfaite : on compare
    # une teinte moyenne, pas une égalité stricte.
    assert np.allclose(first.mean(axis=(0, 1)), (10, 20, 30), atol=5)
    assert np.allclose(second.mean(axis=(0, 1)), (200, 100, 50), atol=5)


def test_read_gives_up_after_max_reconnect_attempts() -> None:
    unreachable = "http://127.0.0.1:1/stream"  # port toujours refusé
    source = MjpegFrameSource(
        unreachable, max_reconnect_attempts=1, reconnect_delay_s=0.01
    )
    assert source.read() is None


def test_consecutive_failures_resets_after_a_successful_frame() -> None:
    jpegs = [_encode((5, 5, 5))]
    with _ToyMjpegServer(jpegs) as server:
        with MjpegFrameSource(server.url) as source:
            assert source.consecutive_failures == 0
            frame = source.read()
            assert frame is not None
            assert source.consecutive_failures == 0
