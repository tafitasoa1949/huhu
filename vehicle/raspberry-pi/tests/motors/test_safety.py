from smart_car.motors.safety import CONTROL_TIMEOUT_MS, decide


def normal(**overrides):
    base = dict(
        requested_speed_pct=0,
        requested_steering_pct=0,
        emergency=False,
        physical_estop_engaged=False,
        ms_since_last_valid_packet=0,
    )
    base.update(overrides)
    return decide(**base)


def test_normal_drive_passes_through_within_bounds():
    decision = normal(requested_speed_pct=42, requested_steering_pct=-15)
    assert (decision.speed_pct, decision.steering_pct, decision.stopped_reason) == (42, -15, None)


def test_speed_and_steering_are_clamped_to_100():
    decision = normal(requested_speed_pct=150, requested_steering_pct=-999)
    assert decision.speed_pct == 100
    assert decision.steering_pct == -100


def test_negative_speed_allowed_for_manual_reverse():
    # docs/mobile-protocol.md : speed_pct va de -100 à +100 en pilotage
    # manuel direct, contrairement à docs/contracts.md (conduite autonome).
    decision = normal(requested_speed_pct=-60)
    assert decision.speed_pct == -60
    assert decision.stopped_reason is None


def test_emergency_forces_stop_even_with_nonzero_request():
    decision = normal(requested_speed_pct=80, requested_steering_pct=50, emergency=True)
    assert (decision.speed_pct, decision.steering_pct) == (0, 0)
    assert decision.stopped_reason == "EMERGENCY_COMMAND"


def test_physical_estop_wins_over_everything_including_emergency_flag():
    decision = normal(emergency=True, physical_estop_engaged=True)
    assert decision.stopped_reason == "PHYSICAL_ESTOP"


def test_timeout_below_threshold_drives_normally():
    decision = normal(
        requested_speed_pct=30, ms_since_last_valid_packet=CONTROL_TIMEOUT_MS - 1
    )
    assert decision.stopped_reason is None
    assert decision.speed_pct == 30


def test_timeout_above_threshold_forces_stop():
    decision = normal(
        requested_speed_pct=30, ms_since_last_valid_packet=CONTROL_TIMEOUT_MS + 1
    )
    assert (decision.speed_pct, decision.steering_pct) == (0, 0)
    assert decision.stopped_reason == "CONTROL_TIMEOUT"


def test_priority_order_estop_beats_timeout():
    decision = normal(physical_estop_engaged=True, ms_since_last_valid_packet=0)
    assert decision.stopped_reason == "PHYSICAL_ESTOP"
