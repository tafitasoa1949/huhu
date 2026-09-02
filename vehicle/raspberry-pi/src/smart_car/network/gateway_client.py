"""Enregistrement/heartbeat côté voiture auprès du Gateway, et petit serveur
HTTP interne `/internal/claim` que le Gateway appelle pour obtenir un jeton.

C'est la voiture qui décide du jeton qu'elle acceptera ensuite en Phase 2,
jamais le Gateway (docs/mobile-protocol.md : « la voiture doit rejeter les
paquets P2P présentant un jeton expiré ou inconnu ») — il n'y a donc qu'une
seule source de vérité sur ce qui est valide.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Callable

DEFAULT_TOKEN_TTL_S = 30
HEARTBEAT_INTERVAL_S = 5.0


class TokenStore:
    """État du jeton de session courant côté voiture.

    Utilisé à la fois par le serveur interne (`issue`, sur claim du
    Gateway) et par le serveur P2P (`current`/`touch`, à chaque paquet reçu)
    — `dict`/attributs Python sont déjà atomiques pour ces accès simples,
    pas besoin de verrou explicite entre le fil HTTP interne et la boucle
    asyncio du contrôle.
    """

    def __init__(self, *, ttl_s: int = DEFAULT_TOKEN_TTL_S, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._token: str | None = None
        self._expires_at: float = 0.0

    def issue(self) -> tuple[str, int]:
        self._token = str(uuid.uuid4())
        self._expires_at = self._clock() + self._ttl_s
        return self._token, self._ttl_s

    def current(self) -> str | None:
        if self._token is None or self._clock() >= self._expires_at:
            return None
        return self._token

    def is_session_active(self) -> bool:
        """Une session de pilotage vit-elle encore ? Rapporté au Gateway à
        chaque heartbeat pour qu'il ne libère pas la voiture sous les pieds
        du pilote en cours (voir `CarRegistry.heartbeat`)."""
        return self.current() is not None

    def touch(self) -> None:
        """Prolonge l'expiration — appelé à chaque paquet P2P valide, pour
        que `expires_in_s` compte depuis le dernier trafic, pas depuis le
        claim initial (docs/mobile-protocol.md)."""
        if self._token is not None:
            self._expires_at = self._clock() + self._ttl_s


def _make_internal_handler(token_store: TokenStore):
    class InternalHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            sys.stderr.write(f"[gateway_client] {self.address_string()} - {format % args}\n")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/internal/claim":
                self.send_error(404)
                return
            token, expires_in_s = token_store.issue()
            # Tracé : un nouveau jeton invalide immédiatement le précédent.
            # Sans cette ligne, une session volée par un second claim est
            # invisible dans le journal — on n'y voit que les paquets du
            # premier pilote brutalement rejetés « jeton invalide ».
            sys.stderr.write(
                f"[gateway_client] nouveau jeton de session émis: {token} "
                f"(valable {expires_in_s}s sans trafic)\n"
            )
            body = json.dumps({"token": token, "expires_in_s": expires_in_s}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return InternalHandler


def start_internal_server(*, host: str, mgmt_port: int, token_store: TokenStore) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, mgmt_port), _make_internal_handler(token_store))
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def _post_json(url: str, payload: dict, *, timeout_s: float = 3.0) -> None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    urllib.request.urlopen(request, timeout=timeout_s).close()


def register(
    *,
    gateway_url: str,
    car_id: str,
    name: str,
    ip: str,
    control_port: int,
    telemetry_port: int,
    video_port: int,
    mgmt_port: int,
) -> None:
    _post_json(
        f"{gateway_url}/api/cars/register",
        {
            "car_id": car_id,
            "name": name,
            "ip": ip,
            "control_port": control_port,
            "telemetry_port": telemetry_port,
            "video_port": video_port,
            "mgmt_port": mgmt_port,
        },
    )


def heartbeat_loop(
    *,
    gateway_url: str,
    car_id: str,
    stop_event: Event,
    session_active_provider: Callable[[], bool] | None = None,
) -> None:
    """Boucle bloquante — à lancer dans son propre fil (`threading.Thread`).
    Un heartbeat manqué n'est pas fatal : le Gateway marquera la voiture
    hors ligne après `HEARTBEAT_TIMEOUT_S`, mais aucune session P2P en cours
    n'est affectée (Phase 2 ne dépend plus du Gateway).

    `session_active_provider` rapporte au Gateway si un pilote roule encore,
    pour qu'il ne libère pas la voiture pendant la session (voir
    `CarRegistry.heartbeat` côté Gateway)."""
    url = f"{gateway_url}/api/cars/{car_id}/heartbeat"
    while not stop_event.is_set():
        try:
            payload = (
                {} if session_active_provider is None else {"session_active": session_active_provider()}
            )
            _post_json(url, payload)
        except (urllib.error.URLError, TimeoutError) as exc:
            sys.stderr.write(f"[gateway_client] heartbeat échoué: {exc}\n")
        stop_event.wait(HEARTBEAT_INTERVAL_S)
