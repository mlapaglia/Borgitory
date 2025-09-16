#!/usr/bin/env python3
"""
Simple script to run ruff linting, formatting, and mypy type checking.
Usage:
  python lint.py check    - Check for linting issues
  python lint.py fix      - Fix auto-fixable linting issues
  python lint.py format   - Format code with ruff
  python lint.py mypy     - Run mypy type checking
  python lint.py all      - Run all checks and formatting
"""

import subprocess
import sys
import os


def run_command(cmd, env=None):
    """Run a command and return the exit code."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)
    return result.returncode


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "check":
        exit_code = run_command(["ruff", "check"])
    elif command == "fix":
        exit_code = run_command(["ruff", "check", "--fix"])
    elif command == "format":
        exit_code = run_command(["ruff", "format"])
    elif command == "mypy":
        # No PYTHONPATH needed anymore!
        exit_code = run_command(
            [".env_borg\\Scripts\\python.exe", "-m", "mypy", "src/borgitory", "tests"]
        )
    elif command == "all":
        # Run all checks and formatting
        print("Running ruff check...")
        exit_code = run_command(["ruff", "check"])
        if exit_code == 0:
            print("Running ruff format...")
            exit_code = run_command(["ruff", "format"])
        if exit_code == 0:
            print("Running mypy type checking...")
            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            exit_code = run_command(
                [".env_borg\\Scripts\\python.exe", "-m", "mypy", "src", "tests"],
                env=env,
            )
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
