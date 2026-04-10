from __future__ import annotations

import importlib
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any


# ----------------------------------------------------------------------
# Ultra-safe settings
# ----------------------------------------------------------------------
ALWAYS_EXIT_SUCCESS = True   # if True: always exit(0) even if things fail
WRITE_ERROR_LOG     = True
PRINT_TRACEBACK     = False  # if True: print traceback to console (still not raising)

# NEW: default to detect-only mode (no pip installs)
detect_only = True

# Optional override via env var (keeps default True if unset/invalid)
#   DETECT_ONLY=0  -> allow installs
#   DETECT_ONLY=1  -> detect only
try:
    v = os.environ.get("DETECT_ONLY")
    if v is not None:
        detect_only = str(v).strip().lower() not in ("0", "false", "no", "off")
except Exception:
    # If env parsing fails for any reason, keep default.
    pass


# Resolve script dir safely (works even if __file__ is missing)
try:
    SCRIPT_DIR = Path(__file__).resolve().parent
except Exception:
    try:
        SCRIPT_DIR = Path.cwd()
    except Exception:
        # Extremely defensive fallback: current directory as a string path
        SCRIPT_DIR = Path(".")

LOG_FILE = SCRIPT_DIR / "bootup_errors.log"


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
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
    except BaseException:
        # If stdout/stderr is broken or printing fails, ignore.
        return


def _log_exception(prefix: str, exc: BaseException) -> None:
    if not WRITE_ERROR_LOG:
        return
    try:
        lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    except BaseException:
        lines = [f"{type(exc).__name__}: {exc}\n"]

    try:
        # Make sure parent exists; if it doesn't, ignore.
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        except BaseException:
            pass

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(prefix + "\n")
            f.write("".join(lines))
    except BaseException:
        # If we cannot write logs (permissions, disk full, FS read-only), ignore.
        return


def _handle_exception(prefix: str, exc: BaseException) -> None:
    # Never raise, never crash
    try:
        _safe_print(f"WARN: {prefix}: {type(exc).__name__}: {exc}")
        if PRINT_TRACEBACK:
            try:
                tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                _safe_print(tb)
            except BaseException:
                pass
        _log_exception(prefix, exc)
    except BaseException:
        # Even exception handling must never fail.
        return


def _safe_import(mod: str) -> bool:
    """
    Attempt to import a module by name.
    - Returns True if import succeeds
    - Returns False if module not found
    - Returns False (and logs) if import fails for other reasons
    Never raises.
    """
    try:
        importlib.import_module(mod)
        return True
    except ModuleNotFoundError:
        return False
    except BaseException as exc:
        _handle_exception(f"Import failed for {mod}", exc)
        return False


def _coerce_cmd(cmd: List[Any]) -> List[str]:
    """
    Best-effort conversion of a command list to list[str].
    Never raises.
    """
    out: List[str] = []
    try:
        for x in cmd:
            try:
                out.append(str(x))
            except BaseException:
                out.append(repr(x))
    except BaseException:
        # If cmd itself is weird, return something safe-ish.
        return [str(cmd)]
    return out


def _run(cmd: List[Any], timeout_s: int = 300) -> Tuple[int, str]:
    """
    Run cmd; return (exit code, combined stdout+stderr).
    Never raises.
    """
    try:
        cmd2 = _coerce_cmd(cmd)

        # Extra safety: refuse to run empty commands
        if not cmd2:
            return 2, "Empty command"

        proc = subprocess.run(
            cmd2,
            capture_output=True,
            text=True,
            timeout=int(timeout_s) if timeout_s else 300,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        # proc.returncode can be None in odd cases; coerce carefully
        try:
            rc = int(proc.returncode) if proc.returncode is not None else 0
        except BaseException:
            rc = 0
        return rc, out

    except subprocess.TimeoutExpired as exc:
        _handle_exception(f"Command timed out: {cmd}", exc)
        return 124, f"Timeout after {timeout_s}s: {cmd}"
    except BaseException as exc:
        _handle_exception(f"Command failed to run: {cmd}", exc)
        return 1, f"Failed to run: {cmd} ({type(exc).__name__}: {exc})"


def _tail_lines(text: str, n: int = 12) -> List[str]:
    try:
        lines = (text or "").splitlines()
        if n <= 0:
            return []
        return lines[-n:]
    except BaseException:
        return []


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    try:
        seen = set()
        out: List[str] = []
        for x in items:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out
    except BaseException:
        # If something goes wrong, return the original list.
        return items


# ----------------------------------------------------------------------
# Install helpers (ultra defensive)
# ----------------------------------------------------------------------
def _pip_usable() -> bool:
    """
    Returns True if `python -m pip --version` works, else False.
    Never raises.
    """
    try:
        rc, _ = _run([sys.executable, "-m", "pip", "--version"], timeout_s=60)
        return rc == 0
    except BaseException as exc:
        _handle_exception("_pip_usable failed", exc)
        return False


def _try_bootstrap_pip() -> bool:
    """
    Best-effort attempt to make pip available via ensurepip.
    Returns True if pip becomes usable, else False.
    Never raises.
    """
    try:
        # If pip is already usable, done.
        if _pip_usable():
            return True

        _safe_print("INFO: pip not usable; trying ensurepip ...")
        rc, out = _run([sys.executable, "-m", "ensurepip", "--upgrade"], timeout_s=180)
        if rc != 0:
            _safe_print("WARN: ensurepip failed.")
            for line in _tail_lines(out, 10):
                _safe_print("      " + line)

        # Re-check
        return _pip_usable()

    except BaseException as exc:
        _handle_exception("_try_bootstrap_pip failed", exc)
        return False


def _install_package(pkg: str) -> bool:
    """
    Return True on success, False if installation failed.
    Never raises.

    NOTE: Installs into whatever interpreter is running this script
    (sys.executable). No venv is created/used.
    """
    try:
        if not pkg or not isinstance(pkg, str):
            _safe_print(f"WARN: invalid package name: {pkg!r}")
            return False

        # Extra safety: verify pip exists before attempting installation
        if not _pip_usable():
            ok = _try_bootstrap_pip()
            if not ok:
                _safe_print("ERROR: pip is not available; cannot install packages.")
                return False

        _safe_print(f"    -> pip install {pkg}")

        rc, out = _run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "--no-input", pkg],
            timeout_s=600,
        )
        if rc == 0:
            return True

        _safe_print("      WARN: pip error (tail):")
        for line in _tail_lines(out, 12):
            _safe_print("      " + line)

        return False

    except BaseException as exc:
        _handle_exception(f"_install_package crashed for {pkg}", exc)
        return False


def _advise_optional() -> None:
    """
    Print optional apt hints for modules that are not importable.
    Never raises.
    """
    try:
        for mod, apt_pkg in OPTIONAL_APT.items():
            try:
                ok = _safe_import(mod)
            except BaseException as exc:
                _handle_exception(f"_safe_import crashed for optional mod {mod}", exc)
                ok = False

            if not ok:
                _safe_print(
                    f"INFO: Optional: sudo apt install {apt_pkg}   (needed for import {mod})"
                )
    except BaseException as exc:
        _handle_exception("_advise_optional failed", exc)
        return


# ----------------------------------------------------------------------
# Main sequence
# ----------------------------------------------------------------------
def bootup_sequence() -> None:
    """
    Never raises.
    """
    try:
        missing_pkgs: List[str] = []
        missing_mods: List[str] = []

        # First detection pass (extra defensive: per-item guard)
        for mod, pkg in REQUIRED.items():
            try:
                ok = _safe_import(mod)
            except BaseException as exc:
                _handle_exception(f"Import check crashed for {mod}", exc)
                ok = False

            if not ok:
                missing_mods.append(mod)
                missing_pkgs.append(pkg)

        missing_pkgs = _dedupe_preserve_order(missing_pkgs)

        if not missing_pkgs:
            _safe_print("OK: Environment already complete - nothing to install.")
            _advise_optional()
            return

        # Detect-only short-circuit (default behavior)
        if detect_only:
            _safe_print("ERROR: Missing mandatory dependencies (detect-only mode; not installing):")
            # Print in a stable, helpful format
            for mod, pkg in REQUIRED.items():
                try:
                    if mod in missing_mods:
                        _safe_print(f"   - import {mod}    (pip: {pkg})")
                except BaseException:
                    # If this display loop breaks, fall back to packages only
                    pass

            _safe_print("INFO: Set detect_only = False (or DETECT_ONLY=0) to allow pip installs.\n")
            _advise_optional()
            return

        # Install mode
        _safe_print("INFO: Installing missing packages ...")
        failed: List[str] = []

        # Install pass (extra defensive: per-package guard)
        for pkg in missing_pkgs:
            try:
                ok = _install_package(pkg)
            except BaseException as exc:
                _handle_exception(f"Install crashed for {pkg}", exc)
                ok = False

            if not ok:
                failed.append(pkg)

        # Second detection pass (verify)
        still_missing_pkgs: List[str] = []
        for mod, pkg in REQUIRED.items():
            try:
                ok = _safe_import(mod)
            except BaseException as exc:
                _handle_exception(f"Verify import crashed for {mod}", exc)
                ok = False

            if not ok:
                still_missing_pkgs.append(pkg)

        still_missing_pkgs = _dedupe_preserve_order(still_missing_pkgs)

        # Results
        if not still_missing_pkgs:
            _safe_print("OK: All mandatory dependencies satisfied.")
        else:
            _safe_print("\nERROR: Some packages could not be installed/imported:")
            for pkg in still_missing_pkgs:
                _safe_print(f"   - {pkg}")
            _safe_print("   Application may not run correctly.\n")

        if failed:
            _safe_print("INFO: Some installs failed. See pip output above for details.")

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
            _safe_print(f"WARN: Unhandled exception suppressed: {exc_type.__name__}: {exc}")
            if PRINT_TRACEBACK:
                try:
                    _safe_print("".join(traceback.format_exception(exc_type, exc, tb)))
                except BaseException:
                    pass
            try:
                _log_exception("Unhandled exception (excepthook)", exc)  # type: ignore[arg-type]
            except BaseException:
                pass
        except BaseException:
            pass

        # Choose an exit code strategy
        try:
            raise SystemExit(0 if ALWAYS_EXIT_SUCCESS else 1)
        except BaseException:
            # If even SystemExit is blocked/suppressed somehow, just return.
            return

    try:
        sys.excepthook = _hook
    except BaseException:
        pass


def main() -> int:
    """
    Returns a process exit code.
    Never raises.
    """
    try:
        # Wrap each "phase" in its own safety cage
        try:
            _install_last_resort_excepthook()
        except BaseException as exc:
            _handle_exception("Failed to install excepthook", exc)

        try:
            bootup_sequence()
        except BaseException as exc:
            _handle_exception("bootup_sequence crashed", exc)

        return 0

    except BaseException as exc:
        _handle_exception("Fatal error in main()", exc)
        return 0 if ALWAYS_EXIT_SUCCESS else 1


if __name__ == "__main__":
    # Absolute top-level catch. This is the "big try/except".
    code: int
    try:
        code = main()
    except BaseException as exc:
        _handle_exception("Top-level crash suppressed", exc)
        code = 0 if ALWAYS_EXIT_SUCCESS else 1

    # Extra safety: never let weird values crash SystemExit(int(...))
    try:
        code_int = int(code)
    except BaseException:
        code_int = 0 if ALWAYS_EXIT_SUCCESS else 1

    try:
        raise SystemExit(code_int)
    except BaseException:
        # If SystemExit is blocked/suppressed somehow, just stop.
        pass