#!/usr/bin/env python3
"""
Simple script to run ruff linting, formatting, mypy type checking, and djLint HTML formatting.
Usage:
  python lint.py <command> [files...]

Commands:
  check    - Check for linting issues
  fix      - Fix auto-fixable linting issues
  format   - Format code with ruff
  mypy     - Run mypy type checking
  html     - Lint HTML templates with djLint
  html-fix - Format HTML templates with djLint
  all      - Run all checks and formatting

If files are provided, only those files are acted on.
If no files are provided, runs on the entire project.
"""

from typing import List, Optional, Dict
import subprocess
import sys
import os


def run_command(cmd: List[str], env: Optional[Dict[str, str]] = None) -> int:
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)
    return result.returncode


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    files = sys.argv[2:]
    py_files = [f for f in files if f.endswith(".py")]
    html_files = [f for f in files if f.endswith((".html", ".htm"))]

    if command == "check":
        exit_code = run_command(["ruff", "check"] + py_files)
    elif command == "fix":
        exit_code = run_command(["ruff", "check", "--fix"] + py_files)
    elif command == "format":
        exit_code = run_command(["ruff", "format"] + py_files)
    elif command == "mypy":
        python_exe = sys.executable
        targets = py_files if py_files else ["src/borgitory"]
        exit_code = run_command([python_exe, "-m", "mypy"] + targets)
    elif command == "html":
        targets = html_files if html_files else ["src/borgitory/templates"]
        exit_code = run_command(["djlint"] + targets)
    elif command == "html-fix":
        targets = html_files if html_files else ["src/borgitory/templates"]
        exit_code = run_command(["djlint"] + targets + ["--reformat"])
    elif command == "all":
        exit_code = 0

        if not files or py_files:
            print("Running ruff check...")
            exit_code = run_command(["ruff", "check", "--fix"] + py_files)

        if exit_code == 0 and (not files or py_files):
            print("Running ruff format...")
            exit_code = run_command(["ruff", "format"] + py_files)

        if exit_code == 0 and (not files or py_files):
            print("Running mypy type checking...")
            env = os.environ.copy()
            env["PYTHONPATH"] = "src"
            python_exe = sys.executable
            targets = py_files if py_files else ["src/borgitory"]
            exit_code = run_command(
                [python_exe, "-m", "mypy"] + targets,
                env=env,
            )

        if exit_code == 0 and (not files or html_files):
            print("Running djLint HTML formatting...")
            targets = html_files if html_files else ["src/borgitory/templates"]
            exit_code = run_command(["djlint"] + targets + ["--reformat"])
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
