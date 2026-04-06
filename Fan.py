import pigpio, time

PWM_PIN = 12
FREQ    = 25000
INVERT  = True     # True if using NPN pull-down (2N2222)

pi = pigpio.pi(); assert pi.connected

def _duty_from_pct(p):
    p = max(0, min(100, p))
    d = int(1_000_000 * (p/100.0))
    return 1_000_000 - d if INVERT else d

def fan_on(percent=50, boost_ms=300):
    # startup boost then settle
    pi.hardware_PWM(PWM_PIN, FREQ, _duty_from_pct(100))
    time.sleep(boost_ms/1000.0)
    pi.hardware_PWM(PWM_PIN, FREQ, _duty_from_pct(percent))

def fan_off():
    # 0% duty to the fan (may still idle on some models)
    pi.hardware_PWM(PWM_PIN, FREQ, _duty_from_pct(0))

def fan_set(percent):
    pi.hardware_PWM(PWM_PIN, FREQ, _duty_from_pct(percent))