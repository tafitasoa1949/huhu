#!/usr/bin/env python3
"""Compare l'ESP32 virtuel au firmware C++, cas par cas.

L'ESP32 virtuel (``smart_car.simulation.esp32_simulator``) est une
transcription Python du firmware. C'est une seconde source de vérité, donc une
source de dérive : une correction faite dans ``steering_controller.cpp`` et
oubliée côté Python rendrait la simulation menteuse, ce qui est pire que pas
de simulation du tout.

Ce script compile la logique C++ et compare les deux implémentations sur une
grille exhaustive de cas. **À relancer après toute modification de
``steering_controller.cpp`` ou ``safety.cpp``.**

Usage::

    python3 tools/check_simulator_parity.py

Ne nécessite qu'un compilateur C++ — ni PlatformIO, ni ArduinoJson, ni carte.
Le décodage du protocole n'est pas couvert ici : les deux jeux de tests
(``tests/test_protocol.py`` et ``test/test_protocol/``) comparent déjà les
mêmes trames littérales.

Code de sortie : 0 si les deux implémentations concordent, 1 sinon.
"""

import itertools
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIRMWARE = REPO / "vehicle" / "esp32-controller"
PYTHON_SRC = REPO / "vehicle" / "raspberry-pi" / "src"

sys.path.insert(0, str(PYTHON_SRC))

from smart_car.simulation.esp32_simulator import (  # noqa: E402
    COMMAND_TIMEOUT_MS,
    MixerConfig,
    SafetyState,
    mix,
)

# Harnais C++ : lit des cas sur stdin, écrit un résultat par ligne.
HARNESS = r"""
#include <cstdio>
#include <iostream>
#include <string>
#include "protocol.h"
#include "safety.h"
#include "steering_controller.h"

int main() {
    std::string kind;
    while (std::cin >> kind) {
        if (kind == "MIX") {
            int speed, steer, gain, minDuty, maxDuty, invL, invR, pivot;
            std::cin >> speed >> steer >> gain >> minDuty >> maxDuty >> invL
                     >> invR >> pivot;
            steering::MixerConfig c;
            c.steering_gain_pct = gain;
            c.min_duty_pct = minDuty;
            c.max_duty_pct = maxDuty;
            c.invert_left = invL != 0;
            c.invert_right = invR != 0;
            c.allow_pivot = pivot != 0;
            steering::WheelDuty d = steering::mix(speed, steer, c);
            std::printf("%d %d\n", d.left_pct, d.right_pct);
        } else if (kind == "SAFETY") {
            unsigned long now, last;
            int received, emergency, rejected, button, hasDist;
            double dist, critical;
            std::cin >> now >> last >> received >> emergency >> rejected
                     >> button >> hasDist >> dist >> critical;
            safety::Inputs in;
            in.now_ms = static_cast<uint32_t>(now);
            in.timeout_ms = protocol::COMMAND_TIMEOUT_MS;
            in.has_received_command = received != 0;
            in.last_command_ms = static_cast<uint32_t>(last);
            in.commanded_emergency = emergency != 0;
            in.last_line_rejected = rejected != 0;
            in.button_pressed = button != 0;
            in.has_local_distance = hasDist != 0;
            in.local_distance_m = static_cast<float>(dist);
            in.critical_distance_m = static_cast<float>(critical);
            safety::Decision d = safety::evaluate(in);
            std::printf("%d %s\n", d.motors_allowed ? 1 : 0,
                        safety::stateName(d.state));
        }
    }
    return 0;
}
"""


def build_harness(workdir: Path) -> Path:
    source = workdir / "harness.cpp"
    source.write_text(HARNESS, encoding="utf-8")
    binary = workdir / "harness"

    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        print("Erreur : ni g++ ni clang++ trouvé.", file=sys.stderr)
        raise SystemExit(2)

    subprocess.run(
        [
            compiler,
            "-std=gnu++17",
            "-Wall",
            "-Wextra",
            "-I",
            str(FIRMWARE / "include"),
            str(source),
            str(FIRMWARE / "src" / "steering_controller.cpp"),
            str(FIRMWARE / "src" / "safety.cpp"),
            "-o",
            str(binary),
        ],
        check=True,
    )
    return binary


def mix_cases():
    """Grille de mélange : vitesses, directions et réglages de calibration."""
    speeds = [0, 1, 10, 30, 45, 60, 100]
    steerings = [-100, -70, -50, -30, -11, -1, 0, 1, 11, 30, 50, 70, 100]
    configs = [
        MixerConfig(),
        MixerConfig(max_duty_pct=100),
        MixerConfig(max_duty_pct=100, min_duty_pct=20),
        MixerConfig(max_duty_pct=40, min_duty_pct=15),
        MixerConfig(steering_gain_pct=50, max_duty_pct=100),
        MixerConfig(steering_gain_pct=0, max_duty_pct=100),
        MixerConfig(max_duty_pct=100, invert_left=True),
        MixerConfig(max_duty_pct=100, invert_right=True),
        MixerConfig(max_duty_pct=100, allow_pivot=True),
    ]
    for speed, steering, config in itertools.product(speeds, steerings, configs):
        yield speed, steering, config


def safety_cases():
    """Grille de sécurité, débordement de millis() compris."""
    times = [
        (10_000, 10_000),
        (10_000, 10_000 - COMMAND_TIMEOUT_MS),
        (10_000, 10_000 - COMMAND_TIMEOUT_MS - 1),
        (10_000, 9_000),
        (0x64, 0xFFFFFF00),  # à cheval sur le débordement
        (0x2BC, 0xFFFFFF00),
    ]
    booleans = [0, 1]
    distances = [(0, 0.0), (1, 0.20), (1, 0.25), (1, 0.30), (1, 1.50)]

    for (now, last), received, emergency, rejected, button, (has_dist, dist) in (
        itertools.product(times, booleans, booleans, booleans, booleans, distances)
    ):
        yield now, last, received, emergency, rejected, button, has_dist, dist


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        binary = build_harness(Path(tmp))

        lines = []
        mixes = list(mix_cases())
        safeties = list(safety_cases())

        for speed, steering, c in mixes:
            lines.append(
                f"MIX {speed} {steering} {c.steering_gain_pct} "
                f"{c.min_duty_pct} {c.max_duty_pct} {int(c.invert_left)} "
                f"{int(c.invert_right)} {int(c.allow_pivot)}"
            )
        for case in safeties:
            now, last, received, emergency, rejected, button, has_dist, dist = case
            lines.append(
                f"SAFETY {now} {last} {received} {emergency} {rejected} "
                f"{button} {has_dist} {dist} 0.25"
            )

        result = subprocess.run(
            [str(binary)],
            input="\n".join(lines) + "\n",
            capture_output=True,
            text=True,
            check=True,
        )
        outputs = result.stdout.split("\n")

    failures = []

    for index, (speed, steering, config) in enumerate(mixes):
        expected_left, expected_right = (
            int(part) for part in outputs[index].split()
        )
        got = mix(speed, steering, config)
        if (got.left_pct, got.right_pct) != (expected_left, expected_right):
            failures.append(
                f"mix(speed={speed}, steering={steering}, "
                f"{config}) : C++ ({expected_left}, {expected_right}) "
                f"vs Python ({got.left_pct}, {got.right_pct})"
            )

    offset = len(mixes)
    for index, case in enumerate(safeties):
        now, last, received, emergency, rejected, button, has_dist, dist = case
        allowed_text, state_name = outputs[offset + index].split()
        expected_allowed = allowed_text == "1"

        got_state, got_allowed = _python_arbitrate(case)
        if got_allowed != expected_allowed or got_state.value != state_name:
            failures.append(
                f"safety(now={now}, last={last}, received={received}, "
                f"emergency={emergency}, rejected={rejected}, "
                f"button={button}, dist={dist if has_dist else None}) : "
                f"C++ ({expected_allowed}, {state_name}) vs "
                f"Python ({got_allowed}, {got_state.value})"
            )

    print(f"mélange différentiel : {len(mixes)} cas comparés")
    print(f"arbitrage de sécurité : {len(safeties)} cas comparés")

    if failures:
        print(f"\n{len(failures)} divergence(s) :\n", file=sys.stderr)
        for failure in failures[:20]:
            print(f"  {failure}", file=sys.stderr)
        if len(failures) > 20:
            print(f"  ... et {len(failures) - 20} autres", file=sys.stderr)
        return 1

    print("\nLes deux implémentations concordent sur tous les cas.")
    return 0


def _python_arbitrate(case) -> tuple[SafetyState, bool]:
    """Reproduit l'appel d'arbitrage à travers l'ESP32 virtuel."""
    from smart_car.simulation.esp32_simulator import (
        DriveMessage,
        ManualClock,
        VirtualEsp32,
    )

    now, last, received, emergency, rejected, button, has_dist, dist = case

    esp32 = VirtualEsp32(clock=ManualClock(0))
    esp32.button_pressed = bool(button)
    esp32.obstacle_distance_m = dist if has_dist else None
    esp32.critical_distance_m = 0.25
    esp32._has_received_command = bool(received)
    esp32._last_command = DriveMessage(emergency=bool(emergency))
    esp32._last_command_ms = last
    esp32._last_line_rejected = bool(rejected)

    state, _error, allowed = esp32._arbitrate(now)
    return state, allowed


if __name__ == "__main__":
    raise SystemExit(main())
