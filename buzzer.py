import pigpio

BUZZER_GPIO = 13       # BCM pin number

pi = pigpio.pi()
if not pi.connected:
    raise SystemExit("pigpiod not running")

pi.set_mode(BUZZER_GPIO, pigpio.OUTPUT)
pi.write(BUZZER_GPIO, 0)          # idle = silent (LOW)


# helper functions
def buzzer_on() -> None:
    """Sound the buzzer continuously."""
    pi.write(BUZZER_GPIO, 1)      # HIGH = transistor ON = buzzer ON

def buzzer_off() -> None:
    """Silence the buzzer."""
    pi.write(BUZZER_GPIO, 0)

def beep(duration_ms: int = 100) -> None:
    """Block for `duration_ms`, then silence."""
    buzzer_on()
    time.sleep(duration_ms / 1000)
    buzzer_off()

def pattern(beeps: int = 2, on_ms: int = 100, off_ms: int = 150) -> None:
    """
    Emit `beeps` short beeps.
    Example: pattern(3)  →  beep-beep-beep
    """
    for _ in range(beeps):
        beep(on_ms)
        time.sleep(off_ms / 1000)


"""
demo when run directly

if __name__ == "__main__":
    try:
        print("Three quick beeps …")
        pattern(3, on_ms=120, off_ms=200)

        print("Continuous alarm for 2 s …")
        buzzer_on()
        time.sleep(2)
        buzzer_off()

    finally:
        buzzer_off()
        pi.stop()
"""