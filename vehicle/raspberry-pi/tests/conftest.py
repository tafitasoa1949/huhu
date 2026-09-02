"""Rend `smart_car` importable sans installation du paquet.

Même principe que `tools/check_simulator_parity.py` : pas de `pip install -e
.` pour l'instant, ce qui suppose un `pyproject.toml` que les trois modules
(vision, décision, contrôle) n'ont pas encore stabilisé ensemble.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
