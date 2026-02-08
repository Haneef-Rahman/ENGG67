# ENGG67

Hardware-focused Python project for ENGG67, targeting Raspberry Pi sensors, status LEDs, and a buzzer. The codebase includes a bootstrapping installer, GPIO-driven buzzer and LED helpers, and a main loop that is intended to orchestrate sensors, fans, and logging.

## Contents

- [main.py](main.py) — entry point and orchestration loop (work-in-progress).
- [bootup.py](bootup.py) — optional dependency installer.
- [buzzer.py](buzzer.py) — buzzer control via pigpio.
- [LED_control.py](LED_control.py) — status LED control via pigpio.

## Requirements

- Raspberry Pi (or compatible) with GPIO access
- Python 3.9+
- pigpio daemon running (`pigpiod`)
- Sensor libraries used in [main.py](main.py):
  - numpy, smbus2, Adafruit_ADS1x15, adafruit-bmp, adafruit-circuitpython-sht31d, pypms, pyserial, RPi.GPIO, pigpio
  - Custom libraries: ENS160, MQ_2_7_138 (installed from GitHub in [bootup.py](bootup.py))

## Setup

1. Start the pigpio daemon:
	- `sudo pigpiod`
2. (Optional) Install dependencies using the bootup helper:
	- Run [bootup.py](bootup.py), or import and call `bootup.bootup_sequence()` from your entry script.

## Usage

Run the main program:

- `python3 main.py`

### Buzzer helper

Import and use:

- `buzzer.buzzer_on()` / `buzzer.buzzer_off()`
- `buzzer.beep(duration_ms=100)`
- `buzzer.pattern(beeps=2, on_ms=100, off_ms=150)`
- `buzzer.alarm(duration_ms=1000)`

### LED helper

Create a `StatusLEDs` instance with a `pigpio.pi()` and use:

- `leds.set("red" | "yellow" | "green" | "blue" | None)`
- `leds.flash_all(times=3, period=0.4)`

## Notes / Current Status

- [main.py](main.py) references functions such as `all_fans_init()`, `vent_fans_start()`, `sensor_fan_start()`, `take_readings()`, `buzzer_ini()`, and `led_init()` that are not yet implemented in this repository.
- The hardware state machine in `hardware.handle_data()` is a placeholder.
- Logging is currently written to `log.txt` in append mode.

## Project Structure

```
bootup.py
buzzer.py
LED_control.py
main.py
README.md
```
