"""Source de frames pour un flux MJPEG HTTP (ESP32-CAM).

Ticket VISION-01 (§6.2 du plan) appliqué à la source réelle du projet : la
caméra de conduite n'est pas une vidéo locale mais l'ESP32-CAM, qui parle
HTTP/MJPEG sur le Wi-Fi (voir `esp32-cam/README.md`). `MjpegFrameSource` lit
ce flux — carte réelle ou `tools/fake_esp32cam_server.py` pendant le
développement, le code client est identique dans les deux cas.

Interface volontairement alignée sur l'attendu du ticket : `read()` renvoie
une frame OpenCV (BGR, `numpy.ndarray`) ou `None`, jamais d'exception pour
une simple coupure réseau — la reconnexion est gérée en interne et journalisée
via `consecutive_failures`. C'est le Wi-Fi qui packet-loss, pas le contrat.
"""

from __future__ import annotations

import re
import socket
import time
import urllib.error
import urllib.request
from types import TracebackType

import cv2
import numpy as np

_BOUNDARY = b"--frame"
_HEADER_END = b"\r\n\r\n"
_CONTENT_LENGTH_RE = re.compile(rb"Content-Length:\s*(\d+)", re.IGNORECASE)


class _ChunkedReader:
    """Tampon de lecture par bloc au-dessus d'une réponse HTTP en flux.

    `http.client.HTTPResponse.read(n)` ne garantit rien sur l'alignement des
    trames : un appel peut renvoyer la fin d'une image et le début de la
    suivante. Ce tampon isole ce découpage du reste du code, qui raisonne en
    "jusqu'à ce marqueur" / "exactement N octets".
    """

    def __init__(self, response, chunk_size: int = 4096) -> None:
        self._response = response
        self._chunk_size = chunk_size
        self._buffer = bytearray()

    def _fill(self) -> bool:
        chunk = self._response.read(self._chunk_size)
        if not chunk:
            return False
        self._buffer.extend(chunk)
        return True

    def read_until(self, marker: bytes) -> bytes:
        while True:
            index = self._buffer.find(marker)
            if index != -1:
                end = index + len(marker)
                data = bytes(self._buffer[:end])
                del self._buffer[:end]
                return data
            if not self._fill():
                raise EOFError("flux MJPEG terminé avant de trouver la frontière")

    def read_exact(self, count: int) -> bytes:
        while len(self._buffer) < count:
            if not self._fill():
                raise EOFError("flux MJPEG terminé avant la fin de l'image annoncée")
        data = bytes(self._buffer[:count])
        del self._buffer[:count]
        return data


class MjpegFrameSource:
    """Lit un flux `multipart/x-mixed-replace` et décode chaque partie en frame.

    Reconnexion automatique sur coupure (câble, redémarrage de la carte,
    Wi-Fi qui décroche) : `read()` ne lève pas, elle renvoie `None` une fois
    `max_reconnect_attempts` épuisé. `None` par défaut = retente indéfiniment,
    ce qui est le bon comportement en conduite ; les tests fixent une valeur
    finie pour ne pas bloquer.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout_s: float = 5.0,
        reconnect_delay_s: float = 1.0,
        max_reconnect_attempts: int | None = None,
    ) -> None:
        self._url = url
        self._timeout_s = timeout_s
        self._reconnect_delay_s = reconnect_delay_s
        self._max_reconnect_attempts = max_reconnect_attempts
        self._response = None
        self._reader: _ChunkedReader | None = None
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        """Nombre d'échecs de lecture/connexion depuis la dernière frame reçue."""
        return self._consecutive_failures

    def read(self) -> np.ndarray | None:
        while True:
            if self._reader is None and not self._reconnect():
                return None
            try:
                return self._read_one_frame()
            except (EOFError, OSError, urllib.error.URLError, socket.timeout) as exc:
                self._disconnect()
                self._consecutive_failures += 1
                print(f"[MjpegFrameSource] flux interrompu ({exc}), reconnexion…")

    def release(self) -> None:
        self._disconnect()

    def __enter__(self) -> "MjpegFrameSource":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def _read_one_frame(self) -> np.ndarray:
        assert self._reader is not None
        self._reader.read_until(_BOUNDARY)
        header_block = self._reader.read_until(_HEADER_END)

        match = _CONTENT_LENGTH_RE.search(header_block)
        if match is None:
            raise EOFError("en-tête de partie MJPEG sans Content-Length")
        length = int(match.group(1))

        payload = self._reader.read_exact(length)
        frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise EOFError("JPEG reçu illisible (trame corrompue)")

        self._consecutive_failures = 0
        return frame

    def _connect(self) -> None:
        self._response = urllib.request.urlopen(self._url, timeout=self._timeout_s)
        self._reader = _ChunkedReader(self._response)

    def _disconnect(self) -> None:
        if self._response is not None:
            try:
                self._response.close()
            except OSError:
                pass
        self._response = None
        self._reader = None

    def _reconnect(self) -> bool:
        attempt = 0
        while self._max_reconnect_attempts is None or attempt < self._max_reconnect_attempts:
            try:
                self._connect()
                return True
            except (OSError, urllib.error.URLError, socket.timeout) as exc:
                attempt += 1
                self._consecutive_failures += 1
                print(
                    f"[MjpegFrameSource] connexion à {self._url} échouée "
                    f"({exc}), tentative {attempt}…"
                )
                time.sleep(self._reconnect_delay_s)
        return False


def _demo() -> int:
    """Démonstration minimale (§6.5 du plan : « commande lisant une vidéo »)."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:81/stream")
    parser.add_argument("--frames", type=int, default=5)
    args = parser.parse_args()

    with MjpegFrameSource(args.url, max_reconnect_attempts=3) as source:
        for index in range(args.frames):
            frame = source.read()
            if frame is None:
                print(f"frame {index}: échec (flux indisponible)")
                return 1
            print(f"frame {index}: shape={frame.shape} dtype={frame.dtype}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo())
