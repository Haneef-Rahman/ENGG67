"""
Example use:

import time
from library.sht31 import sht31

sensor = sht31()

try:
    while True:
        sensor.print_reading()
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    sensor.close()
"""

# sht31.py
import time
from smbus2 import SMBus


class sht31:
    CMD_SINGLE_SHOT_HIGHREP = (0x24, 0x00)

    def __init__(self, bus=1, addr=0x44):
        self.addr = addr
        self.bus = SMBus(bus)

    def _crc8(self, data: bytes) -> int:
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc << 1) ^ 0x31 if (crc & 0x80) else (crc << 1)
                crc &= 0xFF
        return crc

    def read(self):
        self.bus.write_i2c_block_data(
            self.addr,
            self.CMD_SINGLE_SHOT_HIGHREP[0],
            [self.CMD_SINGLE_SHOT_HIGHREP[1]],
        )

        time.sleep(0.020)

        raw = self.bus.read_i2c_block_data(self.addr, 0x00, 6)
        t_raw = bytes(raw[0:2])
        t_crc = raw[2]
        rh_raw = bytes(raw[3:5])
        rh_crc = raw[5]

        if self._crc8(t_raw) != t_crc or self._crc8(rh_raw) != rh_crc:
            raise RuntimeError("CRC mismatch – check wiring and pull-ups")

        t_ticks = int.from_bytes(t_raw, "big")
        rh_ticks = int.from_bytes(rh_raw, "big")

        temperature = -45 + 175 * (t_ticks / 65535)
        humidity = 100 * (rh_ticks / 65535)

        return {
            "temperature": temperature,
            "humidity": humidity,
        }

    def print_reading(self):
        data = self.read()
        print(f"{data['temperature']:6.2f} °C   {data['humidity']:6.2f} %RH")

    def close(self):
        self.bus.close()
