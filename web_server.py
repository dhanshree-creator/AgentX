"""Web interface runner for AgentX.

Run:
    python web_server.py
    python web_server.py --port 8000 --host 127.0.0.1 --open
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser

import uvicorn

from agent.config import load_config
from agent.exceptions import ConfigError
from ui.console import console

APP_NAME = "AgentX"
APP_VERSION = "1.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgentX Modern Web Studio")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--open", action="store_true", help="Automatically open browser tab on start")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload for development")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Verify configuration before launching
    try:
        cfg = load_config()
    except ConfigError as exc:
        console.print(f"[bold red]Configuration Problem:[/bold red] {exc}")
        console.print("[dim]Please ensure .env has valid credentials.[/dim]")
        sys.exit(2)

    url = f"http://{args.host}:{args.port}"

    console.print()
    console.print(f"[bold #E58B58]● {APP_NAME} Web Studio[/bold #E58B58] [dim]v{APP_VERSION}[/dim]")
    console.print(f"[bold cyan]Active Model:[/bold cyan]  [bold white]{cfg.model}[/bold white]")
    console.print(f"[bold cyan]Endpoint:[/bold cyan]      [dim]{cfg.base_url}[/dim]")
    console.print(f"[bold cyan]Web Interface:[/bold cyan] [bold green]{url}[/bold green]")
    console.print("[dim]Press Ctrl+C to stop the web server.[/dim]\n")

    if args.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
