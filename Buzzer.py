import RPi.GPIO as GPIO

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

def _levels(active_high: bool):
    on_level  = GPIO.HIGH if active_high else GPIO.LOW
    off_level = GPIO.LOW  if active_high else GPIO.HIGH
    return on_level, off_level

def Buzzer_on(pin = 21, active_high: bool = True):
    """Turn the buzzer ON by energizing the relay on 'pin'."""
    on_level, _ = _levels(active_high)
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, on_level)

def Buzzer_off(pin = 21, active_high: bool = True):
    """Turn the buzzer OFF by de-energizing the relay on 'pin'."""
    _, off_level = _levels(active_high)
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, off_level)