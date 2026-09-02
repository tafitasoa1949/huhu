from __future__ import annotations

import argparse

from smart_car_gateway.app import create_app


def main() -> int:
    parser = argparse.ArgumentParser(description="Gateway Smart RC Car (docs/mobile-protocol.md, Phase 1)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    app = create_app()
    print(f"Gateway prêt sur http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
