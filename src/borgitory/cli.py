#!/usr/bin/env python3
"""
Command-line interface for Borgitory
"""

import sys
import subprocess
import argparse
import logging
import os
from pathlib import Path
import uvicorn
from dotenv import load_dotenv
from importlib.metadata import version
from importlib import resources


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


def run_migrations() -> bool:
    """Run database migrations before starting the app."""
    print("Running database migrations...")

    try:
        # Ensure data directory exists
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)

        # Find the alembic.ini file in the installed package
        try:
            # Try to find alembic.ini in the package data
            package_dir = resources.files("borgitory")
            alembic_ini_path = package_dir / "alembic.ini"

            # Convert to string and check if file exists
            config_path_str = str(alembic_ini_path)
            if os.path.exists(config_path_str):
                config_path = config_path_str
            else:
                # Try checking with is_file() if available
                try:
                    if alembic_ini_path.is_file():
                        config_path = config_path_str
                    else:
                        config_path = "alembic.ini"
                except (AttributeError, OSError):
                    config_path = "alembic.ini"
        except (ImportError, AttributeError, TypeError, OSError):
            # Fallback for older Python versions or if resources not available
            config_path = "alembic.ini"

        # Run alembic upgrade head with explicit config
        subprocess.run(
            ["alembic", "-c", config_path, "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("Database migrations completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print("Database migration failed!")
        print(f"Error: {e}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        print("Alembic command not found!")
        print("Make sure alembic is installed and available in your PATH")
        return False


def start_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
    log_level: str = "info",
) -> None:
    """Start the Borgitory web server."""
    load_dotenv()

    # Run migrations first
    if not run_migrations():
        print("Exiting due to migration failure")
        sys.exit(1)

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
        "--reload", action="store_true", help="Enable auto-reload for development"
    )
    server_parser.add_argument(
        "--log-level",
        choices=["critical", "error", "warning", "info", "debug"],
        default="info",
        help="Log level (default: info)",
    )

    # Migration command
    subparsers.add_parser("migrate", help="Run database migrations")

    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.command == "serve":
        start_server(
            host=args.host, port=args.port, reload=args.reload, log_level=args.log_level
        )
    elif args.command == "migrate":
        if run_migrations():
            print("Migrations completed successfully")
            sys.exit(0)
        else:
            print("Migration failed")
            sys.exit(1)
    else:
        # Default behavior - start server
        start_server()


if __name__ == "__main__":
    main()
