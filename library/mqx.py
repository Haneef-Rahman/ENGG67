"""
import time
from library.mqx import mq

sensor = mq()

try:
    while True:
        print(mq.mq2(), mq.mq7())
        time.sleep(1)
finally:
    sensor.close()
"""

# mq.py
import time
import lgpio


class mq:
    def __init__(self, bus=1, addr=0x48, mq2_ch=0, mq7_ch=1):
        self.h = lgpio.i2c_open(bus, addr)
        self.mq2_ch = mq2_ch
        self.mq7_ch = mq7_ch

    def read_ch(self, ch):
        msb = [0xC3, 0xD3, 0xE3, 0xF3][ch]
        lgpio.i2c_write_device(self.h, [0x01, msb, 0x83])
        time.sleep(0.02)

        lgpio.i2c_write_device(self.h, [0x00])
        _, d = lgpio.i2c_read_device(self.h, 2)

        raw = (d[0] << 8) | d[1]
        if raw & 0x8000:
            raw -= 0x10000
        return raw

    def mq2(self):
        return self.read_ch(self.mq2_ch)

    def mq7(self):
        return self.read_ch(self.mq7_ch)

    def read(self):
        return {
            "mq2": self.mq2(),
            "mq7": self.mq7(),
        }

    def print_reading(self):
        data = self.read()
        print(f"MQ2: {data['mq2']}  MQ7: {data['mq7']}")

    def close(self):
        lgpio.i2c_close(self.h)
