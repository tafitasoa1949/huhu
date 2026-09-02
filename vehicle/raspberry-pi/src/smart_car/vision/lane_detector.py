"""Détection de piste — tickets VISION-02 à VISION-05 (§6.2 du plan).

Approche de suivi de voie classique : bords (Canny) dans une région
d'intérêt trapézoïdale devant le véhicule, régression des segments de Hough
par côté (gauche/droite selon leur position par rapport au centre de
l'image), puis extrapolation au bas de l'image pour estimer `road_center_x`.

Canny détecte des transitions de contraste, pas une couleur donnée : le
détecteur n'a donc pas besoin de connaître à l'avance si la piste est un
ruban clair sur fond sombre ou l'inverse.
"""

from __future__ import annotations

import cv2
import numpy as np

from smart_car.shared.models import LaneResult

Point = tuple[int, int]


class LaneDetector:
    def __init__(
        self,
        *,
        canny_low: int = 50,
        canny_high: int = 150,
        hough_threshold: int = 40,
        hough_min_line_length: int = 25,
        hough_max_line_gap: int = 100,
        min_vertical_span_px: int = 10,
        roi_top_fraction: float = 0.55,
        roi_top_inset_fraction: float = 0.1,
        confidence_threshold: float = 0.55,
        assumed_half_lane_px: int = 90,
        max_segments_for_full_confidence: int = 8,
    ) -> None:
        # Valeurs de départ génériques (proches des tutoriels de suivi de
        # voie classiques) : à recalibrer une fois de vraies vidéos de piste
        # disponibles (ticket VISION-07), la géométrie réelle du châssis et
        # la hauteur de caméra changeant ce qui compte comme "devant".
        self._canny_low = canny_low
        self._canny_high = canny_high
        self._hough_threshold = hough_threshold
        self._hough_min_line_length = hough_min_line_length
        self._hough_max_line_gap = hough_max_line_gap
        self._min_vertical_span_px = min_vertical_span_px
        self._roi_top_fraction = roi_top_fraction
        self._roi_top_inset_fraction = roi_top_inset_fraction
        self._confidence_threshold = confidence_threshold
        self._assumed_half_lane_px = assumed_half_lane_px
        self._max_segments_for_full_confidence = max_segments_for_full_confidence

    def detect(self, frame: np.ndarray) -> LaneResult:
        height, width = frame.shape[:2]
        image_center_x = width // 2

        edges = self._edges(frame)
        masked = self._apply_roi(edges, height, width)
        segments = cv2.HoughLinesP(
            masked,
            rho=2,
            theta=np.pi / 180,
            threshold=self._hough_threshold,
            minLineLength=self._hough_min_line_length,
            maxLineGap=self._hough_max_line_gap,
        )
        left_points, right_points = self._split_segments(segments, image_center_x)
        road_center_x = self._estimate_road_center(left_points, right_points, height)

        if road_center_x is None:
            return LaneResult(
                detected=False,
                error_px=0.0,
                confidence=0.0,
                road_center_x=None,
                image_center_x=image_center_x,
            )

        confidence = self._estimate_confidence(left_points, right_points)
        return LaneResult(
            detected=confidence >= self._confidence_threshold,
            error_px=float(road_center_x - image_center_x),
            confidence=confidence,
            road_center_x=road_center_x,
            image_center_x=image_center_x,
        )

    def _edges(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        return cv2.Canny(blurred, self._canny_low, self._canny_high)

    def _apply_roi(self, edges: np.ndarray, height: int, width: int) -> np.ndarray:
        # Trapèze couvrant le bas de l'image (le sol devant la voiture) et
        # excluant le haut (arrière-plan hors piste) — forme standard pour
        # une caméra pointée vers l'avant et légèrement vers le bas.
        top_y = int(height * self._roi_top_fraction)
        inset = int(width * self._roi_top_inset_fraction)
        vertices = np.array(
            [[(0, height), (width, height), (width - inset, top_y), (inset, top_y)]],
            dtype=np.int32,
        )
        mask = np.zeros_like(edges)
        cv2.fillPoly(mask, vertices, 255)
        return cv2.bitwise_and(edges, mask)

    def _split_segments(
        self, segments: np.ndarray | None, center_x: int
    ) -> tuple[list[Point], list[Point]]:
        left: list[Point] = []
        right: list[Point] = []
        if segments is None:
            return left, right

        for x1, y1, x2, y2 in segments[:, 0]:
            if abs(int(y2) - int(y1)) < self._min_vertical_span_px:
                continue  # quasi horizontal : pas une bordure de piste
            bucket = left if (int(x1) + int(x2)) / 2 < center_x else right
            bucket.append((int(x1), int(y1)))
            bucket.append((int(x2), int(y2)))
        return left, right

    def _fit_x_at_y(self, points: list[Point], y_ref: int) -> float:
        xs = np.array([p[0] for p in points], dtype=np.float64)
        ys = np.array([p[1] for p in points], dtype=np.float64)
        slope, intercept = np.polyfit(ys, xs, 1)  # x = slope * y + intercept
        return float(slope * y_ref + intercept)

    def _estimate_road_center(
        self, left_points: list[Point], right_points: list[Point], height: int
    ) -> int | None:
        y_ref = height - 1
        if left_points and right_points:
            x_left = self._fit_x_at_y(left_points, y_ref)
            x_right = self._fit_x_at_y(right_points, y_ref)
            return int(round((x_left + x_right) / 2))
        if left_points:
            return int(round(self._fit_x_at_y(left_points, y_ref) + self._assumed_half_lane_px))
        if right_points:
            return int(round(self._fit_x_at_y(right_points, y_ref) - self._assumed_half_lane_px))
        return None

    def _estimate_confidence(self, left_points: list[Point], right_points: list[Point]) -> float:
        left_segments = len(left_points) // 2
        right_segments = len(right_points) // 2
        if left_segments == 0 or right_segments == 0:
            # Une seule bordure visible : road_center_x est un décalage
            # supposé, pas une mesure — volontairement sous le seuil MVP
            # (0.55 par défaut) pour que le moteur de décision ne s'y fie
            # pas seul.
            return 0.5
        segments = min(left_segments + right_segments, self._max_segments_for_full_confidence)
        return 0.5 + 0.5 * segments / self._max_segments_for_full_confidence
