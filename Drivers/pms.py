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

import time
import serial
import struct


class pms:
    def __init__(self, port="/dev/serial0", baudrate=9600, timeout=2):
        self.ser = serial.Serial(port, baudrate, timeout=timeout)

    def valid(self, frame):
        return (sum(frame[:-2]) & 0xFFFF) == struct.unpack(">H", frame[-2:])[0]

    def read(self, max_wait=5):
        start = time.time()

        while time.time() - start < max_wait:
            if self.ser.read(1) != b"\x42":
                continue
            if self.ser.read(1) != b"\x4D":
                continue

            frame = self.ser.read(30)
            full_frame = b"\x42\x4D" + frame

            if len(frame) != 30:
                continue

            if not self.valid(full_frame):
                raise RuntimeError("Bad PMS frame checksum")

            # atmospheric values
            pm1_0, pm2_5, pm10 = struct.unpack(">HHH", frame[8:14])

            return {
                "pm1_0": pm1_0,
                "pm2_5": pm2_5,
                "pm10": pm10,
            }

        raise TimeoutError("PMS sensor timed out waiting for serial data")

    def close(self):
        self.ser.close()
