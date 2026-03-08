#!/usr/bin/env python3
"""
Development server runner for Borgitory
"""

import os
import subprocess
import sys
import uvicorn
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
TAILWIND_CSS = os.path.join(
    REPO_ROOT, "src", "borgitory", "static", "css", "tailwind.css"
)
TAILWIND_INPUT = os.path.join(
    REPO_ROOT, "src", "borgitory", "static", "css", "tailwind-input.css"
)


def _tailwind_needs_build() -> bool:
    if not os.path.exists(TAILWIND_CSS):
        return True
    if not os.path.exists(TAILWIND_INPUT):
        return False
    return os.path.getmtime(TAILWIND_CSS) < os.path.getmtime(TAILWIND_INPUT)


def _ensure_tailwind_built() -> None:
    if not _tailwind_needs_build():
        return
    subprocess.run(
        [sys.executable, "build_tailwind.py"],
        cwd=REPO_ROOT,
        check=True,
    )


if __name__ == "__main__":
    load_dotenv()
    _ensure_tailwind_built()

    print("Starting Borgitory development server on port 8000")
    uvicorn.run(
        "borgitory.main:app", host="0.0.0.0", port=8000, reload=False, log_level="info"
    )
