"""Commande de démonstration — livrable §6.5 du plan.

Lit le flux caméra en continu (vraie ESP32-CAM ou
`tools/fake_esp32cam_server.py`), produit un `PerceptionResult` par frame et
affiche/enregistre l'overlay de débogage. Ne prend aucune décision : ce
n'est pas `main.py`, qui reliera vision, décision et contrôle une fois que
ces deux derniers existeront (Personnes 2 et 3).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from smart_car.vision.mjpeg_source import MjpegFrameSource
from smart_car.vision.overlay import draw_overlay
from smart_car.vision.perception_service import PerceptionService


def run(
    url: str,
    *,
    display: bool,
    save_dir: Path | None,
    max_frames: int | None,
) -> int:
    service = PerceptionService()
    frame_id = 0

    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)

    with MjpegFrameSource(url) as source:
        while max_frames is None or frame_id < max_frames:
            frame = source.read()
            if frame is None:
                print("flux indisponible, arrêt")
                return 1

            frame_id += 1
            result = service.analyze(frame, frame_id)
            print(result)

            annotated = draw_overlay(frame, result.lane)
            if display:
                cv2.imshow("Smart Car - vision", annotated)
                if cv2.waitKey(1) & 0xFF == 27:  # Échap
                    break
            if save_dir is not None:
                cv2.imwrite(str(save_dir / f"frame_{frame_id:05d}.jpg"), annotated)

    if display:
        cv2.destroyAllWindows()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:81/stream")
    parser.add_argument(
        "--display", action="store_true", help="ouvre une fenêtre (nécessite un affichage local)"
    )
    parser.add_argument(
        "--save-dir", type=Path, default=None, help="écrit les frames annotées ici"
    )
    parser.add_argument(
        "--frames", type=int, default=None, help="s'arrête après N frames (illimité par défaut)"
    )
    args = parser.parse_args()
    return run(args.url, display=args.display, save_dir=args.save_dir, max_frames=args.frames)


if __name__ == "__main__":
    raise SystemExit(main())
