from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from Drivers.buzzer import buzzer
from Drivers.ens160 import ens160
from Drivers.fan_control import fan
from Drivers.led_control import leds
from Drivers.mqx import mq
from Drivers.pms import pms
from Drivers.sht31 import sht31

from iaq_scoring import iaq_index

# Optional: only used if Drivers/bmp180.py exists.
try:
    from Drivers.bmp180 import bmp180 as BMP180  # type: ignore
except Exception:
    try:
        from Drivers.bmp180 import BMP180  # type: ignore
    except Exception:
        BMP180 = None


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data.csv"
ERROR_PATH = BASE_DIR / "error.txt"

CSV_FIELDS = [
    "timestamp",
    "cycle",
    "status",
    "iaq",
    "temperature",
    "pressure",
    "humidity",
    "pm1_0",
    "pm2_5",
    "pm10",
    "eCO2",
    "TVOC",
    "mq2",
    "co",
]


def now_string() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_error_file(messages: list[str]) -> None:
    text = [f"[{now_string()}] AQI monitor errors:", ""]
    text.extend(messages)
    ERROR_PATH.write_text("".join(text) + "", encoding="utf-8")


def ensure_csv_exists() -> None:
    if CSV_PATH.exists():
        return

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()


def append_csv(row: dict[str, Any]) -> None:
    ensure_csv_exists()
    clean_row = {field: row.get(field, "") for field in CSV_FIELDS}
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerow(clean_row)


def blink_all_once(status_leds: leds) -> None:
    # Uses the driver internals directly so all LEDs flash together once.
    for led in status_leds._leds.values():
        led.on()
    time.sleep(0.25)
    status_leds.off()
    time.sleep(0.1)


def average_dicts(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {}

    result: dict[str, Any] = {}
    keys = samples[0].keys()

    for key in keys:
        values = [sample[key] for sample in samples if key in sample and sample[key] is not None]
        if not values:
            result[key] = None
        elif all(isinstance(v, (int, float)) for v in values):
            result[key] = round(mean(values), 2)
        else:
            result[key] = values[-1]

    return result


def sample_sensor(sensor: Any, count: int = 5, interval: float = 1.0) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []

    for i in range(count):
        samples.append(sensor.read())
        if i != count - 1:
            time.sleep(interval)
    return average_dicts(samples)


def flatten_readings(
    bmp_data: dict[str, Any] | None,
    sht_data: dict[str, Any],
    pms_data: dict[str, Any],
    ens_data: dict[str, Any],
    mq_data: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {}

    """
    if bmp_data:
        row["bmp180_temperature"] = bmp_data.get("temperature")
        row["bmp180_pressure"] = bmp_data.get("pressure")

    row["sht31_temperature"] = sht_data.get("temperature")
    row["sht31_humidity"] = sht_data.get("humidity")

    row["yysd7_pm1_0"] = pms_data.get("pm1_0")
    row["yysd7_pm2_5"] = pms_data.get("pm2_5")
    row["yysd7_pm10"] = pms_data.get("pm10")

    row["ens160_AQI"] = ens_data.get("AQI")
    row["ens160_eCO2"] = ens_data.get("eCO2")
    row["ens160_TVOC"] = ens_data.get("TVOC")
    row["ens160_temperature"] = ens_data.get("temperature")
    row["ens160_humidity"] = ens_data.get("humidity")

    row["mq2"] = mq_data.get("mq2")
    row["mq7"] = mq_data.get("mq7")
    """
    if bmp_data:
        row["pressure"] = bmp_data.get("pressure")
    row["temperature"] = sht_data.get("temperature")
    row["humidity"] = sht_data.get("humidity")
    row["pm1_0"] = pms_data.get("pm1_0")
    row["pm2_5"] = pms_data.get("pm2_5")
    row["pm10"] = pms_data.get("pm10")
    row["eCO2"] = ens_data.get("eCO2")
    row["TVOC"] = ens_data.get("TVOC")
    row["mq2"] = mq_data.get("mq2")
    row["co"] = mq_data.get("mq7")

    return row

"""
def classify_iaq(row: dict[str, Any]) -> tuple[str, str]:
    # Simple placeholder logic.
    # This is intentionally easy to edit later.
    # MQ-2 and MQ-7 are not used for status yet because the uploaded driver
    # only gives raw ADC values, not calibrated ppm values.
    level = 0
    notes: list[str] = []

    aqi = row.get("ens160_AQI")
    eco2 = row.get("ens160_eCO2")
    tvoc = row.get("ens160_TVOC")
    pm25 = row.get("yysd7_pm2_5")

    if aqi is not None:
        aqi_level = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}.get(int(round(aqi)), 4)
        level = max(level, aqi_level)
        notes.append(f"ENS160 AQI={aqi}")

    if eco2 is not None:
        if eco2 >= 5000:
            level = max(level, 4)
        elif eco2 >= 2000:
            level = max(level, 3)
        elif eco2 >= 1200:
            level = max(level, 2)
        elif eco2 >= 800:
            level = max(level, 1)
        notes.append(f"eCO2={eco2}")

    if tvoc is not None:
        if tvoc >= 2200:
            level = max(level, 4)
        elif tvoc >= 660:
            level = max(level, 3)
        elif tvoc >= 220:
            level = max(level, 2)
        elif tvoc >= 65:
            level = max(level, 1)
        notes.append(f"TVOC={tvoc}")

    if pm25 is not None:
        if pm25 >= 250:
            level = max(level, 4)
        elif pm25 >= 150:
            level = max(level, 3)
        elif pm25 >= 55:
            level = max(level, 2)
        elif pm25 >= 15:
            level = max(level, 1)
        notes.append(f"PM2.5={pm25}")

    statuses = ["excellent", "moderate", "suboptimal", "severe", "lethal"]
    return statuses[level], ", ".join(notes)
"""

def set_status_led(status_leds: leds, status: str) -> None:
    if status == "excellent":
        status_leds.set("blue")
    elif status == "moderate":
        status_leds.set("green")
    elif status == "suboptimal":
        status_leds.set("yellow")
    elif status == "severe":
        status_leds.set("red")
    elif status == "lethal":
        status_leds.blink("red", on_time=0.5, off_time=0.5, n=None, background=True)


def hold_status_for_60_seconds(status: str, alarm: buzzer) -> None:
    for _ in range(60):
        if status == "lethal":
            alarm.on()
            time.sleep(0.2)
            alarm.off()
            time.sleep(0.8)
        else:
            time.sleep(1)


def probe_once(name: str, sensor: Any, errors: list[str]) -> dict[str, Any] | None:
    try:
        return sensor.read()
    except Exception as e:
        errors.append(f"{name}: {e}")
        return None


def cleanup(
    fan_driver: fan | None,
    status_leds: leds | None,
    alarm: buzzer | None,
    sensors: list[Any],
) -> None:
    if alarm is not None:
        try:
            alarm.off()
        except Exception:
            pass

    if status_leds is not None:
        try:
            status_leds.off()
        except Exception:
            pass

    for sensor in sensors:
        try:
            close_fn = getattr(sensor, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass

    if fan_driver is not None:
        try:
            fan_driver.cleanup()
        except Exception:
            pass


def main() -> None:
    fan_driver: fan | None = None
    status_leds: leds | None = None
    alarm: buzzer | None = None
    created_sensors: list[Any] = []

    try:
        status_leds = leds()
        alarm = buzzer()
        fan_driver = fan()

        # Required sensors from the uploaded interfaces.
        sht_sensor = sht31()
        pms_sensor = pms()
        ens_sensor = ens160()
        mq_sensor = mq()
        created_sensors.extend([sht_sensor, pms_sensor, ens_sensor, mq_sensor])

        bmp_sensor = BMP180()
        created_sensors.append(bmp_sensor)

        fan_driver.set_duty(0)
        blink_all_once(status_leds)

        startup_errors: list[str] = []
        probe_once("sht31", sht_sensor, startup_errors)
        probe_once("yysd7/pms", pms_sensor, startup_errors)
        probe_once("ens160", ens_sensor, startup_errors)
        probe_once("mq", mq_sensor, startup_errors)
        probe_once("bmp180", bmp_sensor, startup_errors)

        if startup_errors:
            write_error_file(startup_errors)
            status_leds.exception(background=True)
            fan_driver.set_duty(0)
            print("Startup failed. Check error.txt")
            while True:
                time.sleep(1)

        cycle = 1
        while True:
            fan_driver.set_duty(30)
            status_leds.blink("blue", on_time=0.3, off_time=0.3, n=None, background=True)

            try:
                bmp_data = sample_sensor(bmp_sensor) if bmp_sensor is not None else None
                sht_data = sample_sensor(sht_sensor)
                pms_data = sample_sensor(pms_sensor)

                time.sleep(60)

                ens_data = sample_sensor(ens_sensor)
                mq_data = sample_sensor(mq_sensor)

                print(bmp_data, sht_data, pms_data, ens_data, mq_data)

                row = flatten_readings(bmp_data, sht_data, pms_data, ens_data, mq_data)
                readings = {
                    "co": mq_data["mq7"],
                    "co2": ens_data["eCO2"],
                    "mq2": mq_data["mq2"],
                    "tvoc": ens_data["TVOC"],
                    "pm1": pms_data["pm1_0"],
                    "pm25": pms_data["pm2_5"],
                    "pm10": pms_data["pm10"]
                }
                try:
                    packed = iaq_index(readings)
                except:
                    print("Culprit")
                status = packed["bucket"]
                iaq = packed["iaq"]
                row["iaq"] = iaq
                row["timestamp"] = now_string()
                row["cycle"] = cycle
                row["status"] = status
                #row["notes"] = notes
                append_csv(row)

                print(f"[{row['timestamp']}] cycle={cycle} status={status}")
                set_status_led(status_leds, status)

            except Exception as e:
                error_message = f"[{now_string()}] Runtime cycle {cycle}: {e}"
                write_error_file([error_message])
                status_leds.exception(background=True)
                fan_driver.set_duty(0)
                print(error_message)
                time.sleep(5)
                cycle += 1
                continue

            fan_driver.set_duty(70)
            hold_status_for_60_seconds(status, alarm)
            cycle += 1


    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        cleanup(fan_driver, status_leds, alarm, created_sensors)


if __name__ == "__main__":
    main()

