"""
Example:

from time import sleep

bz = buzzer()

while True:
    bz.on()
    sleep(1)
    bz.off()
    sleep(1)
"""

from time import sleep
from gpiozero import OutputDevice

class buzzer:
    def __init__(self, pin=21):
        self.device = OutputDevice(pin, active_high=True, initial_value=False)

    def on(self):
        self.device.on()

    def off(self):
        self.device.off()

    def toggle(self):
        self.device.toggle()
