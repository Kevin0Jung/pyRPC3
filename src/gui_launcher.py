from __future__ import annotations

import socket
import sys
import os
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.gui import run


def find_available_port(start: int = 8765, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available local port found.")


def main() -> None:
    open_browser = os.environ.get("PYRPC3_NO_BROWSER") != "1"
    run(port=find_available_port(), open_browser=open_browser)


if __name__ == "__main__":
    main()
