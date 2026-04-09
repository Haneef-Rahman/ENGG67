"""
Example use:

from time import sleep
from leds import leds

status = leds()

try:
    status.set("green")      # choose: "green", "blue", "red", "yellow"
    sleep(5)

except Exception:
    status.exception(background=False)
"""

# leds.py
from gpiozero import LED

class leds:
    def __init__(self):
        self._leds = {
            "green": LED(8),
            "blue": LED(11),
            "red": LED(25),
            "yellow": LED(9),
        }

    def off(self):
        for led in self._leds.values():
            led.off()

    def set(self, color: str):
        self.off()
        self._leds[color].on()

    def blink(self, color: str, on_time=0.3, off_time=0.1, n=None, background=True):
        self.off()
        self._leds[color].blink(
            on_time=on_time,
            off_time=off_time,
            n=n,
            background=background,
        )

    def exception(self, on_time=0.2, off_time=0.2, background=True):
        self.blink("yellow", on_time=on_time, off_time=off_time, n=None, background=background)
