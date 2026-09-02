"""Point d'entrée unique de la vision — interface §6.1 du plan.

`PerceptionService.analyze` est la seule chose que le reste du pipeline
(décision) a besoin de connaître : une image entre, un `PerceptionResult`
sort. Ce module ne décide jamais de la vitesse ni de la direction.
"""

from __future__ import annotations

import numpy as np

from smart_car.shared.models import ObstacleResult, PerceptionResult
from smart_car.vision.lane_detector import LaneDetector

_NOT_IMPLEMENTED_OBSTACLE = ObstacleResult(
    detected=False,
    distance_m=None,
    confidence=0.0,
    source="not_implemented",
)
# VISION-09 : la détection d'obstacle n'est pas encore écrite. `detected`
# reste `False`, mais `source="not_implemented"` documente que c'est une
# absence de capteur, pas une mesure "rien devant" — la nuance que
# docs/contracts.md signale comme source de la moitié des bugs d'intégration
# si elle se perd (None/`False` par défaut ne doit jamais se lire comme un
# "voie libre" garanti).


class PerceptionService:
    def __init__(self, lane_detector: LaneDetector | None = None) -> None:
        self._lane_detector = lane_detector or LaneDetector()

    def analyze(self, frame: np.ndarray, frame_id: int) -> PerceptionResult:
        lane = self._lane_detector.detect(frame)
        return PerceptionResult(
            frame_id=frame_id,
            lane=lane,
            obstacle=_NOT_IMPLEMENTED_OBSTACLE,
        )
