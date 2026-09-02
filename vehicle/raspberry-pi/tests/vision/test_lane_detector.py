"""Tests de `smart_car.vision.lane_detector`.

Pas de vidéo réelle disponible pour l'instant (matériel absent, voir
VISION-07 dans `docs/tasks.md`) : les images sont générées, deux segments
convergents représentant les bordures de piste. Reproductible, versionnable
en quelques lignes de code plutôt qu'en fichiers vidéo binaires — un vrai jeu
de vidéos de référence reste à faire une fois la caméra en main.
"""

from __future__ import annotations

import cv2
import numpy as np

from smart_car.vision.lane_detector import LaneDetector

_WIDTH = 320
_HEIGHT = 240


def _make_track_image(center_offset_px: int = 0) -> np.ndarray:
    """Piste à deux bordures convergentes, décalée de `center_offset_px`.

    `center_offset_px` déplace le bas des deux bordures (proche de la
    voiture) tout en gardant leur point de fuite au centre de l'image : cela
    simule une voiture décentrée par rapport à une piste qui va tout droit,
    sans faire varier la largeur apparente de la piste.
    """
    image = np.full((_HEIGHT, _WIDTH, 3), (20, 20, 20), dtype=np.uint8)
    center_x = _WIDTH // 2
    top_y = int(_HEIGHT * 0.55)
    bottom_y = _HEIGHT - 1
    half_width_bottom = 110
    half_width_top = 20
    bottom_center = center_x + center_offset_px

    cv2.line(
        image,
        (bottom_center - half_width_bottom, bottom_y),
        (center_x - half_width_top, top_y),
        (255, 255, 255),
        6,
    )
    cv2.line(
        image,
        (bottom_center + half_width_bottom, bottom_y),
        (center_x + half_width_top, top_y),
        (255, 255, 255),
        6,
    )
    return image


def _make_blank_image() -> np.ndarray:
    return np.full((_HEIGHT, _WIDTH, 3), (30, 30, 30), dtype=np.uint8)


def test_lane_result_contract() -> None:
    """Reprend §6.4 du plan : la sortie respecte le contrat quel que soit le cas."""
    for frame in (_make_track_image(), _make_blank_image()):
        result = LaneDetector().detect(frame)

        assert isinstance(result.detected, bool)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.image_center_x, int)
        assert result.image_center_x == _WIDTH // 2
        if result.detected:
            assert result.road_center_x is not None
            assert result.error_px == (result.road_center_x - result.image_center_x)


def test_centered_track_reports_small_error() -> None:
    frame = _make_track_image(center_offset_px=0)
    result = LaneDetector().detect(frame)

    assert result.detected is True
    assert abs(result.error_px) < 15.0


def test_left_offset_track_reports_negative_error() -> None:
    frame = _make_track_image(center_offset_px=-70)
    result = LaneDetector().detect(frame)

    assert result.detected is True
    assert result.error_px < -20.0


def test_right_offset_track_reports_positive_error() -> None:
    frame = _make_track_image(center_offset_px=70)
    result = LaneDetector().detect(frame)

    assert result.detected is True
    assert result.error_px > 20.0


def test_blank_frame_reports_lane_lost() -> None:
    frame = _make_blank_image()
    result = LaneDetector().detect(frame)

    assert result.detected is False
    assert result.road_center_x is None
    assert result.confidence == 0.0
    assert result.error_px == 0.0
