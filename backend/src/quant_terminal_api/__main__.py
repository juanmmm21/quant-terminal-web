from __future__ import annotations

import argparse
import logging

import uvicorn

from quant_terminal_api.app import create_app
from quant_terminal_api.config import TerminalSettings


def main() -> None:
    parser = argparse.ArgumentParser(description="quant-terminal-api REST server")
    parser.add_argument("--host", default=None, help="bind host (default from TERMINAL_HOST)")
    parser.add_argument(
        "--port", type=int, default=None, help="bind port (default from TERMINAL_PORT)"
    )
    parser.add_argument("--reload", action="store_true", help="enable auto-reload for development")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    settings = TerminalSettings().resolve_paths()
    host = args.host or settings.host
    port = args.port or settings.port
    app = create_app(settings)
    uvicorn.run(app, host=host, port=port, reload=args.reload)


if __name__ == "__main__":
    main()
