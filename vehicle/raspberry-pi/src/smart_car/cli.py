"""Point d'entrée `smart-car-server` — câble Gateway, réseau P2P et moteurs.

Exemple sans matériel, pour valider la chaîne bout-en-bout avant montage
(voir docs/architecture.md) :

    smart-car-server --simulate --car-id car-01 \\
        --ip 192.168.1.20 --gateway-url http://192.168.1.10:8080 \\
        --cam-url http://127.0.0.1:81/stream
"""

from __future__ import annotations

import argparse
import asyncio
import threading

from smart_car.motors.driver import MotorDriver, SimulatedMotorDriver
from smart_car.network import gateway_client
from smart_car.network.p2p_server import P2pServer
from smart_car.network.video_relay import create_server as create_video_server

DEFAULT_CONTROL_PORT = 5005
DEFAULT_TELEMETRY_PORT = 5006
DEFAULT_VIDEO_PORT = 5007
DEFAULT_MGMT_PORT = 9000


def _build_driver(simulate: bool) -> MotorDriver:
    if simulate:
        return SimulatedMotorDriver()
    # Import différé : `gpiozero` n'a besoin d'un vrai GPIO qu'à
    # l'instanciation, pas à l'import — mais autant ne pas exiger le paquet
    # (ni un Raspberry Pi) pour lancer `--simulate` sur un poste de dev.
    from smart_car.motors.gpio_driver import GpioMotorDriver

    return GpioMotorDriver()


async def _run(args: argparse.Namespace) -> None:
    driver = _build_driver(args.simulate)
    token_store = gateway_client.TokenStore()

    gateway_client.start_internal_server(
        host="0.0.0.0", mgmt_port=args.mgmt_port, token_store=token_store
    )
    gateway_client.register(
        gateway_url=args.gateway_url,
        car_id=args.car_id,
        name=args.name,
        ip=args.ip,
        control_port=args.control_port,
        telemetry_port=args.telemetry_port,
        video_port=args.video_port,
        mgmt_port=args.mgmt_port,
    )

    stop_event = threading.Event()
    threading.Thread(
        target=gateway_client.heartbeat_loop,
        kwargs={
            "gateway_url": args.gateway_url,
            "car_id": args.car_id,
            "stop_event": stop_event,
            "session_active_provider": token_store.is_session_active,
        },
        daemon=True,
    ).start()

    video_server = create_video_server(
        host="0.0.0.0",
        port=args.video_port,
        cam_stream_url=args.cam_url,
        token_provider=token_store.current,
    )
    threading.Thread(target=video_server.serve_forever, daemon=True).start()

    server = P2pServer(
        driver=driver,
        control_port=args.control_port,
        telemetry_port=args.telemetry_port,
        token_provider=token_store.current,
        on_valid_packet=token_store.touch,
    )
    await server.start()
    print(
        f"{args.car_id} prêt — control:{args.control_port} "
        f"telemetry:{args.telemetry_port} video:{args.video_port} "
        f"(gateway:{args.gateway_url}, simulate={args.simulate})"
    )

    try:
        await asyncio.Event().wait()  # tourne indéfiniment, jusqu'à Ctrl+C
    finally:
        stop_event.set()
        video_server.shutdown()
        await server.stop()
        driver.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--car-id", default="car-01")
    parser.add_argument("--name", default="Smart RC Car #1")
    parser.add_argument(
        "--ip", required=True, help="IP de ce Raspberry Pi, telle que le Gateway la communique à l'app"
    )
    parser.add_argument("--gateway-url", required=True, help="ex: http://192.168.1.10:8080")
    parser.add_argument("--cam-url", default="http://127.0.0.1:81/stream", help="flux MJPEG de l'ESP32-CAM")
    parser.add_argument("--control-port", type=int, default=DEFAULT_CONTROL_PORT)
    parser.add_argument("--telemetry-port", type=int, default=DEFAULT_TELEMETRY_PORT)
    parser.add_argument("--video-port", type=int, default=DEFAULT_VIDEO_PORT)
    parser.add_argument("--mgmt-port", type=int, default=DEFAULT_MGMT_PORT)
    parser.add_argument(
        "--simulate", action="store_true", help="pilote un SimulatedMotorDriver au lieu du GPIO réel"
    )
    args = parser.parse_args()

    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
