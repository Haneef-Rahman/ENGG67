"""
Usage:

from time import sleep

f = fan()
f.set_duty(30)
sleep(2)
f.cleanup()

"""


#!/usr/bin/env python3
from __future__ import annotations

import sys

try:
    import lgpio  # type: ignore
except ModuleNotFoundError:
    sys.exit("ERROR: python3 -m pip install lgpio")

class fan:
    def __init__(self, pin=12, freq=2000, invert=True):
        self.pin = pin
        self.freq = freq
        self.invert = invert

        try:
            self.h = lgpio.gpiochip_open(0)
        except Exception as e:
            sys.exit(f"ERROR: cannot open /dev/gpiochip0 – {e}")

        claimed = False
        for fn_name in ("set_mode", "gpio_claim_output", "gpioClaimOutput"):
            if hasattr(lgpio, fn_name):
                fn = getattr(lgpio, fn_name)
                try:
                    if fn_name == "set_mode":
                        fn(self.h, self.pin, lgpio.MODE_OUTPUT)
                    else:
                        fn(self.h, self.pin, 0)
                    claimed = True
                    break
                except Exception:
                    pass

        if not claimed:
            lgpio.gpiochip_close(self.h)
            sys.exit(f"ERROR: could not set BCM {self.pin} as output with this lgpio build.")

    def _effective_pct(self, percent: float) -> float:
        percent = max(0.0, min(100.0, percent))
        return 100.0 - percent if self.invert else percent

    def set_duty(self, percent: float) -> None:
        pct = self._effective_pct(percent)
        lgpio.tx_pwm(self.h, self.pin, self.freq, pct, 0, 0)

    def cleanup(self) -> None:
        try:
            self.set_duty(0)
            if hasattr(lgpio, "wave_tx_stop"):
                lgpio.wave_tx_stop(self.h)
        finally:
            lgpio.gpiochip_close(self.h)


if __name__ == "__main__":
    f = fan()

    print("\nType a number 0-100 to set duty, or 'q' to quit.")

    try:
        while True:
            try:
                cmd = input("fan%> ").strip()
            except EOFError:
                break

            if cmd.lower().startswith("q"):
                break

            try:
                pct = float(cmd)
            except ValueError:
                print("  ↳ enter a number 0-100 or q")
                continue

            f.set_duty(pct)
            print(f"  ↳ duty set to {pct:.1f} %")
    except KeyboardInterrupt:
        pass
    finally:
        f.cleanup()
        print("\nFan stopped, GPIO released. Bye!")
