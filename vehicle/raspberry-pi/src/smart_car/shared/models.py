"""Contrats communs — section 4 du plan de développement, docs/contracts.md.

Une seule définition, importée par la vision, la décision et le contrôle
plutôt que redéclarée à chaque endroit. Toute modification doit être validée
par les trois personnes (voir docs/contracts.md, note « Changement de
contrat »).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, get_args

Action = Literal[
    "FORWARD",
    "TURN_LEFT",
    "TURN_RIGHT",
    "STOP",
    "EMERGENCY_STOP",
]

_ACTIONS: tuple[str, ...] = get_args(Action)


@dataclass(frozen=True)
class LaneResult:
    detected: bool
    error_px: float
    confidence: float
    road_center_x: Optional[int]
    image_center_x: int


@dataclass(frozen=True)
class ObstacleResult:
    detected: bool
    distance_m: Optional[float]
    confidence: float
    source: str


@dataclass(frozen=True)
class PerceptionResult:
    frame_id: int
    lane: LaneResult
    obstacle: ObstacleResult


@dataclass(frozen=True)
class DriveCommand:
    sequence: int
    action: Action
    speed_pct: int
    steering_pct: int
    emergency: bool


@dataclass(frozen=True)
class Telemetry:
    sequence: int
    status: str
    obstacle_distance_m: Optional[float]
    battery_pct: Optional[int]
    left_rpm: Optional[float]
    right_rpm: Optional[float]
    error: Optional[str]


def validate_command(command: DriveCommand) -> None:
    """Lève `ValueError` si `command` viole le contrat (docs/contracts.md, §Validation).

    Les bornes ne sont pas vérifiées à la construction du dataclass : les
    tests du protocole doivent pouvoir fabriquer des commandes hors plage
    pour vérifier qu'elles sont bien rejetées (scénario S10). C'est cette
    fonction, appelée par les contrôleurs avant tout envoi, qui fait
    respecter le contrat.
    """
    if command.action not in _ACTIONS:
        raise ValueError(f"action must be one of {_ACTIONS}, got {command.action!r}")
    if not 0 <= command.speed_pct <= 100:
        raise ValueError("speed_pct must be between 0 and 100")
    if not -100 <= command.steering_pct <= 100:
        raise ValueError("steering_pct must be between -100 and 100")
    if command.emergency and command.speed_pct != 0:
        raise ValueError("Emergency command must have speed_pct = 0")
    if command.sequence < 0:
        raise ValueError("sequence must not be negative")
