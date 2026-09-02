"""Test de contrat pour `PerceptionService` (§6.1 du plan)."""

from __future__ import annotations

import numpy as np

from smart_car.vision.perception_service import PerceptionService


def test_analyze_returns_contract_compliant_result() -> None:
    frame = np.full((240, 320, 3), (30, 30, 30), dtype=np.uint8)

    result = PerceptionService().analyze(frame, frame_id=7)

    assert result.frame_id == 7
    assert isinstance(result.lane.detected, bool)
    assert 0.0 <= result.lane.confidence <= 1.0
    # VISION-09 non fait : l'obstacle doit le dire, pas simuler une mesure.
    assert result.obstacle.detected is False
    assert result.obstacle.distance_m is None
    assert result.obstacle.source == "not_implemented"
