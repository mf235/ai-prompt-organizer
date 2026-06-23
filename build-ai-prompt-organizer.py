from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

APP_NAME = "ai-prompt-organizer"
APP_VERSION = "v1.5.0"
ROOT_DIR = Path(__file__).resolve().parent
SOURCE_SCRIPT = ROOT_DIR / f"{APP_NAME}.py"
OUTPUT_DIR = ROOT_DIR / APP_NAME
ZIP_PATH = ROOT_DIR / f"{APP_NAME}-{APP_VERSION}.zip"
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"
SPEC_PATH = ROOT_DIR / f"{APP_NAME}.spec"
RESOURCES_DIR = ROOT_DIR / "resources"
EXE_ICON = RESOURCES_DIR / "icons" / "app.ico"
WINDOW_ICON = RESOURCES_DIR / "icons" / "window.png"
PYINSTALLER_CACHE_DIR = ROOT_DIR / f".pyinstaller-cache-{APP_VERSION}"


def log(message: str) -> None:
    print(message, flush=True)


def fail(message: str, code: int = 1) -> None:
    log(f"[ERROR] {message}")
    raise SystemExit(code)


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_module(package_name: str, import_name: str | None = None) -> None:
    import_name = import_name or package_name
    try:
        __import__(import_name)
        return
    except Exception:
        pass

    log(f"[INFO] {package_name} was not found. Installing...")
    install = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", package_name])
    if install.returncode != 0:
        fail(f"Failed to install {package_name}.")


def ensure_pyinstaller() -> None:
    check = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if check.returncode == 0:
        return

    log("[INFO] PyInstaller was not found. Installing...")
    install = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])
    if install.returncode != 0:
        fail("Failed to install PyInstaller.")


def find_source_script() -> Path:
    if SOURCE_SCRIPT.exists():
        return SOURCE_SCRIPT
    fail(f"Source script was not found: {SOURCE_SCRIPT.name}")
    raise AssertionError("unreachable")


def build_exe(source_script: Path) -> None:
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(PYINSTALLER_CACHE_DIR)

    add_data_arg = f"{RESOURCES_DIR}{os.pathsep}resources"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(ROOT_DIR),
        "--icon",
        str(EXE_ICON),
        "--add-data",
        add_data_arg,
        "--hidden-import",
        "cv2",
        "--collect-all",
        "cv2",
        str(source_script),
    ]

    log("[INFO] Building EXE with PyInstaller...")
    result = subprocess.run(command, env=env)
    if result.returncode != 0:
        fail("PyInstaller build failed.")


def create_zip() -> None:
    exe_path = DIST_DIR / f"{APP_NAME}.exe"
    if not exe_path.exists():
        fail(f"EXE was not created: {exe_path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe_path, OUTPUT_DIR / f"{APP_NAME}.exe")

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in sorted(OUTPUT_DIR.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(ROOT_DIR))


def main() -> int:
    os.chdir(ROOT_DIR)
    log("")
    log("========================================")
    log(f"AI Prompt Organizer build {APP_VERSION}")
    log("========================================")
    log("")
    log(f"[INFO] Python: {sys.executable}")
    log(f"[INFO] Python version: {sys.version.split()[0]}")

    source_script = find_source_script()
    log(f"[INFO] Source: {source_script}")

    if not EXE_ICON.exists():
        fail(f"EXE icon was not found: {EXE_ICON}")
    if not WINDOW_ICON.exists():
        fail(f"Window icon was not found: {WINDOW_ICON}")
    if not RESOURCES_DIR.exists():
        fail(f"Resources folder was not found: {RESOURCES_DIR}")

    log(f"[INFO] EXE icon: {EXE_ICON}")
    log(f"[INFO] Window icon: {WINDOW_ICON}")
    log(f"[INFO] EXE icon SHA256: {sha256(EXE_ICON)}")

    ensure_pyinstaller()
    ensure_module("opencv-python", "cv2")

    log("")
    log("[INFO] Cleaning old build files...")
    for path in [OUTPUT_DIR, ZIP_PATH, BUILD_DIR, DIST_DIR, SPEC_PATH, PYINSTALLER_CACHE_DIR]:
        remove_path(path)

    log("")
    build_exe(source_script)

    log("")
    log("[INFO] Creating ZIP...")
    create_zip()

    log("")
    log("========================================")
    log("Build complete")
    log("========================================")
    log(f"ZIP: {ZIP_PATH}")
    log("Contents:")
    log(f"  {APP_NAME}/{APP_NAME}.exe")
    log("")
    log("If Explorer still shows an old icon, extract the ZIP to a new folder.")
    log("Windows may cache icons by path and exe name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
