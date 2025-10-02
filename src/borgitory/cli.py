#!/usr/bin/env python3
"""
Command-line interface for Borgitory
"""

import sys
import argparse
import logging
import uvicorn
from dotenv import load_dotenv
from importlib.metadata import version


def get_version() -> str:
    """Get the current version of borgitory."""
    return version("borgitory")


def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )


def start_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
    log_level: str = "info",
) -> None:
    """Start the Borgitory web server."""
    load_dotenv()

    print(f"Starting Borgitory server on {host}:{port}")
    uvicorn.run(
        "borgitory.main:app", host=host, port=port, reload=reload, log_level=log_level
    )


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Borgitory - Web-based BorgBackup management interface",
        prog="borgitory",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {get_version()}"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Server command
    server_parser = subparsers.add_parser("serve", help="Start the web server")
    server_parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    server_parser.add_argument(
        "--port", "-p", type=int, default=8000, help="Port to bind to (default: 8000)"
    )
    server_parser.add_argument(
        "--log-level",
        choices=["critical", "error", "warning", "info", "debug"],
        default="info",
        help="Log level (default: info)",
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.command == "serve":
        start_server(host=args.host, port=args.port, log_level=args.log_level)
    else:
        # Default behavior - start server
        start_server()


if __name__ == "__main__":
    main()
