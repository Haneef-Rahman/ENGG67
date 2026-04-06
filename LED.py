# led_control.py
import time
import RPi.GPIO as GPIO

RED = 25
YELLOW = 9
GREEN = 8
BLUE = 11

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

def LED_on(pin: int, on: bool = True, active_high: bool = True):
    """
    Turn a single LED on or off.
    - pin: BCM GPIO number
    - on: True to turn LED on, False to turn it off
    - active_high: True if LED anode goes to GPIO (GPIO HIGH = ON),
                   False if LED cathode goes to GPIO (GPIO LOW = ON)
    """
    GPIO.setup(pin, GPIO.OUT)
    if active_high:
        GPIO.output(pin, GPIO.HIGH if on else GPIO.LOW)
    else:
        GPIO.output(pin, GPIO.LOW if on else GPIO.HIGH)

def LED_blink(pin: int,
              on_time: float = 0.2,
              off_time: float = 0.8,
              n: int = 5,
              active_high: bool = True,
              end_on: bool = False):
    """
    Blink a single LED.
    - pin: BCM GPIO number
    - on_time/off_time: seconds
    - n: number of cycles; if n <= 0, blink forever (Ctrl+C to stop)
    - active_high: wiring polarity (see LED_on)
    - end_on: leave LED on after blinking (default leaves it off)
    """
    GPIO.setup(pin, GPIO.OUT)
    on_level  = GPIO.HIGH if active_high else GPIO.LOW
    off_level = GPIO.LOW  if active_high else GPIO.HIGH

    if n is None or n <= 0:
        try:
            while True:
                GPIO.output(pin, on_level);  time.sleep(on_time)
                GPIO.output(pin, off_level); time.sleep(off_time)
        except KeyboardInterrupt:
            GPIO.output(pin, off_level)
        return

    for _ in range(n):
        GPIO.output(pin, on_level);  time.sleep(on_time)
        GPIO.output(pin, off_level); time.sleep(off_time)

    GPIO.output(pin, on_level if end_on else off_level)