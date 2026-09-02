"""Overlay de débogage — ticket VISION-06 (§6.2 du plan).

Superpose sur une frame le centre image, le centre de piste estimé et le
statut de détection : ce qui permet de comprendre une erreur visuellement,
sans relire du texte de log en regard de la vidéo.
"""

from __future__ import annotations

import cv2
import numpy as np

from smart_car.shared.models import LaneResult

_IMAGE_CENTER_COLOR = (255, 128, 0)  # BGR : bleu
_ROAD_CENTER_OK_COLOR = (0, 200, 0)  # BGR : vert
_ROAD_CENTER_UNSURE_COLOR = (0, 165, 255)  # BGR : orange
_TEXT_OK_COLOR = (0, 200, 0)
_TEXT_LOST_COLOR = (0, 0, 255)


def draw_overlay(frame: np.ndarray, lane: LaneResult) -> np.ndarray:
    """Renvoie une copie annotée de `frame` — n'altère jamais l'original."""
    annotated = frame.copy()
    height = annotated.shape[0]

    cv2.line(
        annotated,
        (lane.image_center_x, 0),
        (lane.image_center_x, height),
        _IMAGE_CENTER_COLOR,
        1,
    )

    if lane.road_center_x is not None:
        color = _ROAD_CENTER_OK_COLOR if lane.detected else _ROAD_CENTER_UNSURE_COLOR
        cv2.line(annotated, (lane.road_center_x, 0), (lane.road_center_x, height), color, 2)

    status = "OK" if lane.detected else "PERTE"
    text = f"{status}  err={lane.error_px:+.0f}px  conf={lane.confidence:.2f}"
    text_color = _TEXT_OK_COLOR if lane.detected else _TEXT_LOST_COLOR

    # Contour noir puis remplissage coloré : lisible quel que soit le fond.
    cv2.putText(annotated, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(annotated, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 1, cv2.LINE_AA)

    return annotated
