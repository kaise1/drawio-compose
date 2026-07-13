from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .errors import DrawioComposeError


def find_drawio_cli() -> Path | None:
    configured = os.environ.get("DRAWIO_CLI")
    candidates = [configured] if configured else []
    candidates.extend(shutil.which(name) for name in ("drawio", "draw.io", "diagrams.net"))
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates.extend(
            [
                r"C:\Program Files\draw.io\draw.io.exe",
                local / "Programs" / "draw.io" / "draw.io.exe",
            ]
        )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def render_diagram(source: Path, output: Path) -> None:
    executable = find_drawio_cli()
    if executable is None:
        raise DrawioComposeError(
            "draw.io Desktop CLI was not found; install draw.io or set DRAWIO_CLI"
        )
    extension = output.suffix.lower().lstrip(".")
    if extension not in {"png", "svg", "pdf"}:
        raise DrawioComposeError("render output must end in .png, .svg, or .pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(executable),
        "--export",
        "--format",
        extension,
        "--output",
        str(output.resolve()),
        str(source.resolve()),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise DrawioComposeError(f"draw.io render failed: {details}")
    if not output.is_file():
        raise DrawioComposeError(f"draw.io did not create {output}")
