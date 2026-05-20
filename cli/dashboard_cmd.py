"""exo dashboard — launch the web UI."""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel

console = Console()


def run(*, fleet_path: str, port: int = 8080, host: str = "127.0.0.1",
        open_browser: bool = True) -> None:
    try:
        import uvicorn  # noqa: F401
        from fastapi import FastAPI  # noqa: F401
    except ImportError:
        console.print("[red]exo dashboard needs fastapi + uvicorn.[/red]")
        console.print("Install with: [cyan]pip install fastapi uvicorn jinja2[/cyan]")
        sys.exit(2)

    from exo_runtime.dashboard import create_app
    import uvicorn

    p = Path(fleet_path)
    if not p.exists():
        console.print(f"[red]fleet.yaml not found at: {fleet_path}[/red]")
        console.print("Run [cyan]exo discover[/cyan] first, or specify --fleet <path>.")
        sys.exit(2)

    app = create_app(default_fleet_path=p)

    url = f"http://{host}:{port}/"
    console.print(Panel.fit(
        f"[bold cyan]exo dashboard[/bold cyan]\n"
        f"Fleet:   [yellow]{p}[/yellow]\n"
        f"URL:     [cyan]{url}[/cyan]  ·  [cyan]{url}pulse[/cyan]\n"
        f"Stop:    Ctrl+C",
        border_style="cyan",
    ))

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host=host, port=port, log_level="info")
