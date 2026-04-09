from __future__ import annotations

import importlib
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# ----------------------------------------------------------------------
# Ultra-safe settings
# ----------------------------------------------------------------------
ALWAYS_EXIT_SUCCESS = True  # if True: always exit(0) even if things fail
WRITE_ERROR_LOG     = True
PRINT_TRACEBACK     = False  # if True: print traceback to console (still not raising)

# Resolve script dir safely (works even if __file__ is missing)
try:
    SCRIPT_DIR = Path(__file__).resolve().parent
except Exception:
    SCRIPT_DIR = Path.cwd()

LOG_FILE = SCRIPT_DIR / "bootup_errors.log"

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
VENV_DIR = SCRIPT_DIR / "iaq-env"

# Linux / Pi default. (If you ever run this on Windows, you’d change this.)
VENV_PY  = VENV_DIR / "bin" / "python3"

# Required  {import-name: PyPI package}
REQUIRED: Dict[str, str] = {
    "adafruit_blinka": "adafruit-blinka",
    "adafruit_ahtx0":  "adafruit-circuitpython-ahtx0",
    "adafruit_ens160": "adafruit-circuitpython-ens160",
    "RPi.GPIO":        "RPi.GPIO",
    "smbus2":          "smbus2",
    "numpy":           "numpy",
    "serial":          "pyserial",
}

# Optional  {import-name: apt package   (only a hint)}
OPTIONAL_APT: Dict[str, str] = {
    "lgpio":  "python3-lgpio",
    "pigpio": "python3-pigpio",
}

# ----------------------------------------------------------------------
# Low-level safe utilities
# ----------------------------------------------------------------------
def _safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        # If stdout is broken, ignore.
        pass


def _log_exception(prefix: str, exc: BaseException) -> None:
    if not WRITE_ERROR_LOG:
        return
    try:
        lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(prefix + "\n")
            f.write("".join(lines))
    except Exception:
        # If we cannot write logs, ignore.
        pass


def _handle_exception(prefix: str, exc: BaseException) -> None:
    # Never raise, never crash
    try:
        _safe_print(f"⚠️  {prefix}: {type(exc).__name__}: {exc}")
        if PRINT_TRACEBACK:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            _safe_print(tb)
        _log_exception(prefix, exc)
    except Exception:
        # Even exception handling must never fail.
        pass


def _safe_import(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except ModuleNotFoundError:
        return False
    except BaseException as exc:
        _handle_exception(f"Import failed for {mod}", exc)
        return False


def _run(cmd: List[str], timeout_s: int = 300) -> Tuple[int, str]:
    """
    Run cmd; return (exit code, combined stdout+stderr).
    Never raises.
    """
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return int(proc.returncode or 0), out
    except subprocess.TimeoutExpired as exc:
        _handle_exception(f"Command timed out: {cmd}", exc)
        return 124, f"Timeout after {timeout_s}s: {cmd}"
    except BaseException as exc:
        _handle_exception(f"Command failed to run: {cmd}", exc)
        return 1, f"Failed to run: {cmd} ({type(exc).__name__}: {exc})"


def _safe_check_call(cmd: List[str], timeout_s: int = 600) -> bool:
    """
    Like subprocess.check_call but never raises.
    """
    try:
        subprocess.run(cmd, check=True, timeout=timeout_s)
        return True
    except subprocess.TimeoutExpired as exc:
        _handle_exception(f"check_call timed out: {cmd}", exc)
        return False
    except subprocess.CalledProcessError as exc:
        _handle_exception(f"check_call failed (exit={exc.returncode}): {cmd}", exc)
        return False
    except BaseException as exc:
        _handle_exception(f"check_call failed to run: {cmd}", exc)
        return False


# ----------------------------------------------------------------------
# Venv + install helpers (ultra defensive)
# ----------------------------------------------------------------------
def _ensure_venv() -> None:
    """
    Create the venv once and re-exec inside it.
    This function never raises.
    """
    try:
        # If VENV_PY doesn't exist, we're not in venv (or venv not created yet)
        in_venv = (Path(sys.executable).resolve() == VENV_PY.resolve())
    except Exception:
        in_venv = False

    if in_venv:
        return  # already inside

    try:
        if not VENV_DIR.exists():
            _safe_print(f"🔧  Creating venv at {VENV_DIR} …")
            ok = _safe_check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
            if not ok:
                _safe_print("❌  Could not create venv. Continuing without venv.")
                return

        # Upgrade packaging tools (idempotent)
        if not VENV_PY.exists():
            _safe_print(f"❌  Expected venv python not found at: {VENV_PY}")
            _safe_print("    Continuing without venv.")
            return

        _safe_print("🔧  Upgrading pip/setuptools/wheel in the venv …")
        ok = _safe_check_call(
            [str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]
        )
        if not ok:
            _safe_print("⚠️  pip tooling upgrade failed. Continuing anyway.")

        # Re-exec ourselves using venv's interpreter
        _safe_print("🔄  Re-executing inside the venv …\n")
        try:
            os.execv(str(VENV_PY), [str(VENV_PY)] + sys.argv)
        except BaseException as exc:
            # execv only returns/raises on failure
            _handle_exception("os.execv failed (cannot re-exec into venv)", exc)
            _safe_print("⚠️  Continuing in the current interpreter.")
            return

    except BaseException as exc:
        _handle_exception("_ensure_venv failed", exc)
        # Continue without venv
        return


def _install_package(pkg: str) -> bool:
    """
    Return True on success, False if installation failed.
    Never raises.
    """
    try:
        _safe_print(f"    → pip install {pkg}")
        rc, out = _run([sys.executable, "-m", "pip", "install", "--upgrade", "--no-input", pkg])
        if rc == 0:
            return True

        _safe_print("      ⚠️  pip error:")
        try:
            lines = out.strip().splitlines()
            for line in lines[-8:]:
                _safe_print("      " + line)
        except Exception:
            pass
        return False
    except BaseException as exc:
        _handle_exception(f"_install_package crashed for {pkg}", exc)
        return False


def _advise_optional() -> None:
    try:
        for mod, apt_pkg in OPTIONAL_APT.items():
            ok = _safe_import(mod)
            if not ok:
                _safe_print(
                    f"ℹ️  Optional:  sudo apt install {apt_pkg}   "
                    f"(needed for  import {mod})"
                )
    except BaseException as exc:
        _handle_exception("_advise_optional failed", exc)


# ----------------------------------------------------------------------
# Main sequence
# ----------------------------------------------------------------------
def bootup_sequence() -> None:
    """
    Never raises.
    """
    try:
        missing: List[str] = []

        # first detection pass
        for mod, pkg in REQUIRED.items():
            ok = _safe_import(mod)
            if not ok:
                missing.append(pkg)

        if not missing:
            _safe_print("✅  Environment already complete – nothing to install.")
            _advise_optional()
            return

        _safe_print("⏳  Installing missing packages …")
        failed: List[str] = []

        # install pass
        for pkg in missing:
            if not _install_package(pkg):
                failed.append(pkg)

        # second detection pass (verify)
        still_missing: List[str] = []
        for mod, pkg in REQUIRED.items():
            ok = _safe_import(mod)
            if not ok:
                still_missing.append(pkg)

        # results
        if not still_missing:
            _safe_print("✅  All mandatory dependencies satisfied.")
        else:
            _safe_print("\n❌  Some packages could not be installed/imported:")
            for pkg in still_missing:
                _safe_print(f"   • {pkg}")
            _safe_print("   Application may not run correctly.\n")

        if failed:
            _safe_print("📝  See pip output above for error details.")

        _advise_optional()

    except BaseException as exc:
        _handle_exception("bootup_sequence failed", exc)
        return


# ----------------------------------------------------------------------
def _install_last_resort_excepthook() -> None:
    """
    If *anything* bubbles up to the interpreter, suppress traceback.
    This is a last resort. We still do normal try/except in main.
    """
    def _hook(exc_type, exc, tb):
        try:
            _safe_print(f"⚠️  Unhandled exception suppressed: {exc_type.__name__}: {exc}")
            if PRINT_TRACEBACK:
                _safe_print("".join(traceback.format_exception(exc_type, exc, tb)))
            _log_exception("Unhandled exception (excepthook)", exc)
        except Exception:
            pass

        # Choose an exit code strategy
        try:
            if ALWAYS_EXIT_SUCCESS:
                raise SystemExit(0)
            raise SystemExit(1)
        except BaseException:
            # If even that fails, do nothing.
            return

    try:
        sys.excepthook = _hook
    except Exception:
        pass


def main() -> int:
    """
    Returns a process exit code.
    Never raises.
    """
    try:
        _install_last_resort_excepthook()

        _ensure_venv()       # may replace the current process via execv
        bootup_sequence()    # runs only if we are still here

        return 0
    except BaseException as exc:
        _handle_exception("Fatal error in main()", exc)
        return 0 if ALWAYS_EXIT_SUCCESS else 1


if __name__ == "__main__":
    # Absolute top-level catch. This is the "big try/except".
    try:
        code = main()
    except BaseException as exc:
        _handle_exception("Top-level crash suppressed", exc)
        code = 0 if ALWAYS_EXIT_SUCCESS else 1

    try:
        raise SystemExit(int(code))
    except BaseException:
        # If SystemExit is blocked/suppressed somehow, just stop.
        pass