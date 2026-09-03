"""Affiche les mesures de l'ADXL345.

    smart-car-accel                # temps réel : une ligne réécrite sur place, 20 fois par seconde
    smart-car-accel --log          # une ligne par seconde, qui défile (journal)
    smart-car-accel --samples 10   # dix relevés puis sortie

Les valeurs sont **en m/s²**, trois axes plus la norme du vecteur. Au repos,
cette norme doit tourner autour de 9,81 : c'est la gravité, que
l'accéléromètre mesure comme n'importe quelle autre accélération (voir
`sensors/adxl345.py`). Une norme proche de 0 signale un capteur en veille ou
mal lu, pas une voiture immobile.
"""

from __future__ import annotations

import argparse
import sys
import time

from smart_car.sensors.adxl345 import Acceleration, Adxl345

# Le capteur échantillonne à `hardware.ADXL345_OUTPUT_RATE_HZ` (100 Hz) :
# rafraîchir 20 fois par seconde donne un affichage fluide sans jamais relire
# deux fois le même échantillon.
LIVE_INTERVAL_S = 0.05
LOG_INTERVAL_S = 1.0

HEADER = "t(s)      x(m/s²)  y(m/s²)  z(m/s²)  |a|(m/s²)"


def _format_row(elapsed_s: float, accel: Acceleration) -> str:
    return (
        f"{elapsed_s:7.1f}  {accel.x:8.2f} {accel.y:8.2f} {accel.z:8.2f} "
        f"{accel.magnitude:9.2f}"
    )


def run(*, interval_s: float, max_samples: int | None, live: bool) -> int:
    # Réécrire la ligne sur place n'a de sens que sur un terminal : redirigé
    # vers un fichier ou un `grep`, `\r` produirait une seule ligne illisible
    # où tous les relevés se sont écrasés. Dans ce cas on retombe sur le
    # journal qui défile.
    live = live and sys.stdout.isatty()

    with Adxl345() as sensor:
        print(HEADER, flush=True)
        start = time.monotonic()
        sample = 0
        try:
            while max_samples is None or sample < max_samples:
                accel = sensor.read()
                row = _format_row(time.monotonic() - start, accel)
                if live:
                    # `\r` sans saut de ligne : la même ligne est réécrite.
                    print(f"\r{row}", end="", flush=True)
                else:
                    print(row, flush=True)
                sample += 1
                if max_samples is not None and sample >= max_samples:
                    break
                # Cadencé sur `start`, pas sur un `sleep(interval)` sec : la
                # lecture et l'affichage prennent un peu de temps, qui
                # dériverait sinon d'un relevé à l'autre.
                time.sleep(max(0.0, start + sample * interval_s - time.monotonic()))
        finally:
            if live:
                print()  # laisse le dernier relevé visible, curseur à la ligne
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="fait défiler une ligne par relevé au lieu de réécrire sur place",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help=(
            f"secondes entre deux relevés (défaut : {LIVE_INTERVAL_S} en temps réel, "
            f"{LOG_INTERVAL_S} avec --log)"
        ),
    )
    parser.add_argument(
        "--samples", type=int, default=None, help="s'arrête après N relevés (illimité par défaut)"
    )
    args = parser.parse_args()

    live = not args.log
    interval_s = args.interval if args.interval is not None else (LIVE_INTERVAL_S if live else LOG_INTERVAL_S)
    try:
        return run(interval_s=interval_s, max_samples=args.samples, live=live)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
