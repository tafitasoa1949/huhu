"""Rend `smart_car_gateway` importable sans installation du paquet — même
principe que `vehicle/raspberry-pi/tests/conftest.py`.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
