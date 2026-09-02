#!/usr/bin/env python3
"""Sert un flux MJPEG identique à celui de l'ESP32-CAM, sans la carte.

La carte réelle (``vehicle/esp32-cam/src/main.cpp``) expose un seul point d'accès,
``GET /stream``, qui répond en ``multipart/x-mixed-replace`` : chaque partie
est une image JPEG précédée de sa frontière et de son en-tête. Ce script
reproduit exactement ce format à partir d'une webcam locale, pour que le
futur client Python (celui qui produira ``PerceptionResult``) se développe et
se teste sans attendre le matériel — même principe que l'ESP32 virtuel pour
``vehicle/esp32-controller`` (voir ``docs/communication-protocol.md``, §8).

Le client ne doit rien savoir de la différence : il pointe sur
``http://127.0.0.1:81/stream`` pendant le développement, puis sur
``http://<ip-carte>:81/stream`` une fois la carte disponible, sans changer
une ligne de code.

Usage::

    python3 tools/fake_esp32cam_server.py
    python3 tools/fake_esp32cam_server.py --camera-index 1 --port 8081

Puis, dans un navigateur ou le futur client : ``http://127.0.0.1:81/stream``.

Ne reproduit que ce que le firmware fait aujourd'hui (un seul endpoint, pas
de limite de cadence) : si le firmware gagne un ``/snapshot`` ou un plafond
de fps, ce script doit être mis à jour en même temps pour ne pas mentir sur
ce qu'il simule.
"""

from __future__ import annotations

import argparse
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame"
STREAM_BOUNDARY = b"\r\n--frame\r\n"


def make_handler(capture: cv2.VideoCapture, jpeg_quality: int):
    class StreamHandler(BaseHTTPRequestHandler):
        # Un log par requête suffit ; le flot d'images ne doit pas noyer la
        # console (contrairement au log par défaut de BaseHTTPRequestHandler,
        # qui logguerait quasiment rien ici puisqu'il n'y a qu'une requête
        # GET par client, mais on le rend explicite).
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            sys.stderr.write(f"[fake-esp32cam] {self.address_string()} - "
                              f"{format % args}\n")

        def do_GET(self) -> None:  # noqa: N802 (nom imposé par la stdlib)
            # La carte réelle ne reçoit jamais de query string (le Raspberry
            # Pi l'appelle sans paramètre, voir mjpeg_source.py) ; on
            # tolère `?...` ici uniquement parce que ce script sert aussi de
            # relais de test local à la place du Pi non encore écrit, et que
            # l'app y ajoute `?token=...` (docs/mobile-protocol.md).
            if self.path != "/stream" and not self.path.startswith("/stream?"):
                self.send_error(404, "Seul /stream existe, comme sur la carte réelle")
                return

            self.send_response(200)
            self.send_header("Content-Type", STREAM_CONTENT_TYPE)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            try:
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        print("Webcam : lecture échouée, arrêt du flux",
                              file=sys.stderr)
                        return

                    ok, encoded = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
                    )
                    if not ok:
                        continue
                    payload = encoded.tobytes()

                    part_header = (
                        f"Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(payload)}\r\n\r\n"
                    ).encode("ascii")

                    self.wfile.write(STREAM_BOUNDARY)
                    self.wfile.write(part_header)
                    self.wfile.write(payload)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # Client déconnecté (fermeture du client, Ctrl+C côté
                # navigateur) : le firmware réel traite ça comme une fin de
                # requête normale, pas une erreur — même choix ici.
                pass

    return StreamHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-index", type=int, default=0,
                         help="index de la webcam locale (défaut : 0)")
    parser.add_argument("--port", type=int, default=81,
                         help="port HTTP, 81 par défaut comme la carte réelle")
    parser.add_argument("--width", type=int, default=320,
                         help="largeur demandée à la webcam (défaut : 320, comme QVGA)")
    parser.add_argument("--height", type=int, default=240,
                         help="hauteur demandée à la webcam (défaut : 240, comme QVGA)")
    parser.add_argument("--jpeg-quality", type=int, default=80,
                         help="qualité JPEG OpenCV, 0-100 où 100 = meilleure "
                              "(échelle inverse de celle du firmware, qui va "
                              "de 0=meilleure à 63=pire ; défaut : 80)")
    args = parser.parse_args()

    capture = cv2.VideoCapture(args.camera_index)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    # Beaucoup de backends (DirectShow/MSMF sur Windows notamment) tamponnent
    # plusieurs frames en interne par défaut, ce qui ajoute un retard fixe
    # avant même que ce script n'entre en jeu — sans rapport avec la latence
    # du relais qu'on cherche à mesurer. Pas garanti supporté par tous les
    # backends, d'où le silence si la propriété est ignorée.
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not capture.isOpened():
        print(f"Impossible d'ouvrir la webcam d'index {args.camera_index}.",
              file=sys.stderr)
        return 1

    # Une frame de préchauffe : certaines webcams renvoient une première
    # image noire ou corrompue le temps que l'exposition se stabilise.
    capture.read()
    time.sleep(0.2)

    handler = make_handler(capture, args.jpeg_quality)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)

    print(f"Faux ESP32-CAM prêt : http://127.0.0.1:{args.port}/stream")
    print("Ctrl+C pour arrêter.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        capture.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
