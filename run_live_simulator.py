"""Launcher for RIP-X Live Interactive Simulator (Packet Tracer Simulation Mode)."""

from __future__ import annotations

import functools
import http.server
import os
from pathlib import Path
import socketserver
import threading
import webbrowser

PORT = 8080
VISUALIZER_DIR = Path(__file__).parent / "visualizer"


def main() -> None:
    os.chdir(VISUALIZER_DIR)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(VISUALIZER_DIR))

    with socketserver.TCPServer(("", PORT), handler) as httpd:
        url = f"http://localhost:{PORT}"
        print(f"============================================================")
        print(f"  RIP-X Live Interactive Simulator (Packet Tracer Mode)")
        print(f"  Running at: {url}")
        print(f"  Press Ctrl+C in terminal to stop server.")
        print(f"============================================================")

        # Open in default web browser automatically
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down simulator server.")


if __name__ == "__main__":
    main()
