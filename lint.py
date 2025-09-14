#!/usr/bin/env python3
"""
Simple script to run ruff linting and formatting.
Usage:
  python lint.py check    - Check for linting issues
  python lint.py fix      - Fix auto-fixable linting issues
  python lint.py format   - Format code with ruff
"""

import subprocess
import sys


def run_command(cmd):
    """Run a command and return the exit code."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
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
    elif command == "all":
        # Run all checks and formatting
        print("Running ruff check...")
        exit_code = run_command(["ruff", "check"])
        if exit_code == 0:
            print("Running ruff format...")
            exit_code = run_command(["ruff", "format"])
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
