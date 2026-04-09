"""
import time
from library import pms

sensor = pms()

try:
    while True:
        pm1_5 = sensor.read()[pm1_0]
        #also pm2_5 pm10
        sensor.print_reading()
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    sensor.close()
"""


import serial
import struct


class pms:
    def __init__(self, port="/dev/serial0", baudrate=9600, timeout=2):
        self.ser = serial.Serial(port, baudrate, timeout=timeout)

    def valid(self, frame):
        return (sum(frame[:-2]) & 0xFFFF) == struct.unpack(">H", frame[-2:])[0]

    def read(self):
        while True:
            if self.ser.read(1) != b"\x42":
                continue
            if self.ser.read(1) != b"\x4D":
                continue

            frame = self.ser.read(30)
            full_frame = b"\x42\x4D" + frame

            if len(frame) != 30 or not self.valid(full_frame):
                raise RuntimeError("Bad frame")

            pm1_0, pm2_5, pm10 = struct.unpack(">HHH", frame[2:8])

            return {
                "pm1_0": pm1_0,
                "pm2_5": pm2_5,
                "pm10": pm10,
            }

    def print_reading(self):
        data = self.read()
        print(
            f"PM1.0={data['pm1_0']}  "
            f"PM2.5={data['pm2_5']}  "
            f"PM10={data['pm10']} µg/m³"
        )

    def close(self):
        self.ser.close()
