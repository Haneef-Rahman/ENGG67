from __future__ import annotations
import time
import pigpio


# ------------------------------------------------------------
# user settings – edit here only if you re-wire
# ------------------------------------------------------------
GPIO_RED    = 24
GPIO_YELLOW = 25
GPIO_GREEN  = 16
GPIO_BLUE   = 20
ACTIVE_HIGH = True          # flip if you ever wire them active-LOW
# ------------------------------------------------------------

_OFF = 0 if ACTIVE_HIGH else 1
_ON  = 1 - _OFF

_PIN_FOR_COLOUR = {
    "red":    GPIO_RED,
    "yellow": GPIO_YELLOW,
    "green":  GPIO_GREEN,
    "blue":   GPIO_BLUE,
}


class StatusLEDs:
    """Exactly one of four LEDs may be on; colour names are used."""
    def __init__(self, pi: pigpio.pi) -> None:
        self.pi = pi
        self._pins = list(_PIN_FOR_COLOUR.values())
        for p in self._pins:
            pi.set_mode(p, pigpio.OUTPUT)
            pi.write(p, _OFF)

    # --------------- public API --------------------------------------
    def set(self, colour: str | None) -> None:
        """
        Turn on the requested colour; pass None to turn all off.
            colour ∈ {'red', 'yellow', 'green', 'blue'}
        """
        colour = None if colour is None else colour.lower()
        for name, pin in _PIN_FOR_COLOUR.items():
            self.pi.write(pin, _ON if name == colour else _OFF)

    def flash_all(self, times: int = 3, period: float = 0.4) -> None:
        """Blink all LEDs together for a power-on self-test."""
        for _ in range(times):
            for p in self._pins:
                self.pi.write(p, _ON)
            time.sleep(period / 2)
            self.set(None)
            time.sleep(period / 2)


"""
demo when invoked directly

if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpiod not running")

    leds = StatusLEDs(pi)

    try:
        leds.flash_all()
        for colour in ("red", "yellow", "green", "blue"):
            leds.set(colour)
            time.sleep(0.7)
        leds.set(None)
    except KeyboardInterrupt:
        pass
    finally:
        leds.set(None)
        pi.stop()
"""