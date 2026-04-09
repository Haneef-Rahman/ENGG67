"""
Example use:

import time
from library.ens160 import ens160

sensor = ens160()

while True:
    sensor.print_reading()
    time.sleep(1)
"""

# ens160.py
import board
import busio
import adafruit_ens160
import adafruit_ahtx0


class ens160:
    def __init__(self, i2c_freq=400_000):
        self.i2c = busio.I2C(board.SCL, board.SDA, frequency=i2c_freq)

        self.ens = adafruit_ens160.ENS160(self.i2c)
        self.ens.operation_mode = adafruit_ens160.MODE_STANDARD

        self.aht = adafruit_ahtx0.AHTx0(self.i2c)

    def read(self):
        t_c = self.aht.temperature
        rh = self.aht.relative_humidity

        self.ens.temperature = t_c
        self.ens.humidity = rh

        return {
            "AQI": self.ens.AQI,
            "eCO2": self.ens.eCO2,
            "TVOC": self.ens.TVOC,
            "temperature": t_c,
            "humidity": rh,
        }

    def print_reading(self):
        data = self.read()
        print(
            f"AQI  : {data['AQI']:2d}  (1=good … 5=unhealthy)   "
            f"eCO₂ : {data['eCO2']:4d} ppm   "
            f"TVOC : {data['TVOC']:4d} ppb   "
            f"[{data['temperature']:5.2f} °C  {data['humidity']:5.1f} %RH]"
        )
