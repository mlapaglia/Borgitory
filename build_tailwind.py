"""
Build script for Tailwind CSS using the standalone CLI.

Downloads the platform-appropriate Tailwind CSS v3 standalone binary
and compiles the CSS from template sources. No Node.js required.

Usage:
    python build_tailwind.py            # One-shot build (minified)
    python build_tailwind.py --watch    # Watch mode for development
    python build_tailwind.py --clean    # Remove cached binary and output
"""

import os
import platform
import stat
import subprocess
import sys
import urllib.request

TAILWIND_VERSION = "3.4.17"
TAILWIND_RELEASE_URL = (
    f"https://github.com/tailwindlabs/tailwindcss/releases/download"
    f"/v{TAILWIND_VERSION}"
)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tailwindcss")
INPUT_CSS = os.path.join(
    "src", "borgitory", "static", "css", "tailwind-input.css"
)
OUTPUT_CSS = os.path.join(
    "src", "borgitory", "static", "css", "tailwind.css"
)


def get_binary_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        arch = "x64" if machine in ("amd64", "x86_64") else "arm64"
        return f"tailwindcss-windows-{arch}.exe"
    elif system == "darwin":
        arch = "arm64" if machine == "arm64" else "x64"
        return f"tailwindcss-macos-{arch}"
    else:
        arch = "arm64" if machine in ("aarch64", "arm64") else "x64"
        return f"tailwindcss-linux-{arch}"


def get_binary_path() -> str:
    name = get_binary_name()
    return os.path.join(CACHE_DIR, name)


def download_binary() -> str:
    binary_path = get_binary_path()
    if os.path.exists(binary_path):
        return binary_path

    os.makedirs(CACHE_DIR, exist_ok=True)
    name = get_binary_name()
    url = f"{TAILWIND_RELEASE_URL}/{name}"

    print(f"Downloading Tailwind CSS v{TAILWIND_VERSION} standalone CLI...")
    print(f"  {url}")
    urllib.request.urlretrieve(url, binary_path)

    if not binary_path.endswith(".exe"):
        st = os.stat(binary_path)
        os.chmod(binary_path, st.st_mode | stat.S_IEXEC)

    print(f"  Saved to {binary_path}")
    return binary_path


def clean():
    import shutil

    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
        print(f"Removed {CACHE_DIR}")
    if os.path.exists(OUTPUT_CSS):
        os.remove(OUTPUT_CSS)
        print(f"Removed {OUTPUT_CSS}")


def build(watch: bool = False):
    binary = download_binary()

    cmd = [binary, "-i", INPUT_CSS, "-o", OUTPUT_CSS]
    if watch:
        cmd.append("--watch")
    else:
        cmd.append("--minify")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    args = sys.argv[1:]

    if "--clean" in args:
        clean()
        return

    watch = "--watch" in args
    rc = build(watch=watch)
    sys.exit(rc)


if __name__ == "__main__":
    main()
