from smart_car.network.gateway_client import TokenStore


def make_store(now: list[float], ttl_s: int = 30) -> TokenStore:
    return TokenStore(ttl_s=ttl_s, clock=lambda: now[0])


def test_no_token_before_first_issue():
    store = make_store([0.0])
    assert store.current() is None


def test_issue_returns_a_usable_token():
    store = make_store([0.0])
    token, expires_in_s = store.issue()
    assert token
    assert expires_in_s == 30
    assert store.current() == token


def test_token_expires_without_traffic():
    now = [0.0]
    store = make_store(now)
    store.issue()
    now[0] = 31.0
    assert store.current() is None


def test_touch_extends_expiry_from_last_traffic_not_from_claim():
    now = [0.0]
    store = make_store(now)
    token, _ = store.issue()
    now[0] = 25.0
    store.touch()
    now[0] = 50.0  # 25s après touch, < ttl (30s) -> encore valide
    assert store.current() == token


def test_reissue_replaces_previous_token():
    store = make_store([0.0])
    first, _ = store.issue()
    second, _ = store.issue()
    assert first != second
    assert store.current() == second
