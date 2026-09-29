"""Launcher for the RIP-X live visualizer, driven by the Python RIP engine.

Equivalent to ``python -m ripx.server --open``. Opening ``visualizer/index.html``
directly still works, but then the browser falls back to its standalone engine.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ripx.server import main  # noqa: E402


if __name__ == "__main__":
    main(["--open", *sys.argv[1:]])
