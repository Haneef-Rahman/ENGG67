"""
Example:

import time
from library.bmp180 import bmp180

sensor = bmp180()

try:
    while True:
        sensor.print_reading()
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    sensor.close()
"""

# library/bmp180.py
import time
from smbus2 import SMBus


class bmp180:
    BMP180_ADDR = 0x77

    REG_CONTROL = 0xF4
    REG_RESULT = 0xF6

    CMD_READ_TEMP = 0x2E
    CMD_READ_PRESSURE = 0x34

    def __init__(self, bus_num=1, oss=0):
        self.bus = SMBus(bus_num)
        self.oss = oss
        self._read_calibration_data()

    def _read_signed_16bit(self, reg):
        msb = self.bus.read_byte_data(self.BMP180_ADDR, reg)
        lsb = self.bus.read_byte_data(self.BMP180_ADDR, reg + 1)
        value = (msb << 8) + lsb
        if value > 32767:
            value -= 65536
        return value

    def _read_unsigned_16bit(self, reg):
        msb = self.bus.read_byte_data(self.BMP180_ADDR, reg)
        lsb = self.bus.read_byte_data(self.BMP180_ADDR, reg + 1)
        return (msb << 8) + lsb

    def _read_calibration_data(self):
        self.AC1 = self._read_signed_16bit(0xAA)
        self.AC2 = self._read_signed_16bit(0xAC)
        self.AC3 = self._read_signed_16bit(0xAE)
        self.AC4 = self._read_unsigned_16bit(0xB0)
        self.AC5 = self._read_unsigned_16bit(0xB2)
        self.AC6 = self._read_unsigned_16bit(0xB4)
        self.B1 = self._read_signed_16bit(0xB6)
        self.B2 = self._read_signed_16bit(0xB8)
        self.MB = self._read_signed_16bit(0xBA)
        self.MC = self._read_signed_16bit(0xBC)
        self.MD = self._read_signed_16bit(0xBE)

    def _read_raw_temp(self):
        self.bus.write_byte_data(self.BMP180_ADDR, self.REG_CONTROL, self.CMD_READ_TEMP)
        time.sleep(0.005)
        msb = self.bus.read_byte_data(self.BMP180_ADDR, self.REG_RESULT)
        lsb = self.bus.read_byte_data(self.BMP180_ADDR, self.REG_RESULT + 1)
        return (msb << 8) + lsb

    def _read_raw_pressure(self):
        self.bus.write_byte_data(
            self.BMP180_ADDR,
            self.REG_CONTROL,
            self.CMD_READ_PRESSURE + (self.oss << 6),
        )
        time.sleep(0.005 if self.oss == 0 else 0.026)

        msb = self.bus.read_byte_data(self.BMP180_ADDR, self.REG_RESULT)
        lsb = self.bus.read_byte_data(self.BMP180_ADDR, self.REG_RESULT + 1)
        xlsb = self.bus.read_byte_data(self.BMP180_ADDR, self.REG_RESULT + 2)

        return ((msb << 16) + (lsb << 8) + xlsb) >> (8 - self.oss)

    def read(self):
        ut = self._read_raw_temp()
        up = self._read_raw_pressure()

        x1 = ((ut - self.AC6) * self.AC5) / 32768.0
        x2 = (self.MC * 2048.0) / (x1 + self.MD)
        b5 = x1 + x2
        temperature = (b5 + 8.0) / 16.0 / 10.0

        b6 = b5 - 4000.0
        x1 = (self.B2 * (b6 * b6 / 4096.0)) / 2048.0
        x2 = (self.AC2 * b6) / 2048.0
        x3 = x1 + x2
        b3 = ((self.AC1 * 4.0 + x3) * (2 ** self.oss) + 2.0) / 4.0

        x1 = (self.AC3 * b6) / 8192.0
        x2 = (self.B1 * (b6 * b6 / 4096.0)) / 65536.0
        x3 = (x1 + x2 + 2.0) / 4.0
        b4 = (self.AC4 * (x3 + 32768.0)) / 32768.0
        b7 = (up - b3) * (50000.0 / (2 ** self.oss))

        if b7 < 0x80000000:
            p = (b7 * 2.0) / b4
        else:
            p = (b7 / b4) * 2.0

        x1 = (p / 256.0) ** 2
        x1 = (x1 * 3038.0) / 65536.0
        x2 = (-7357.0 * p) / 65536.0
        p = p + (x1 + x2 + 3791.0) / 16.0

        pressure = p
        altitude = 44330.0 * (1.0 - (pressure / 101325.0) ** (1.0 / 5.255))

        return {
            "temperature": temperature,
            "pressure": pressure,
            "altitude": altitude,
        }

    def read_altitude(self, sea_level_pa=101325.0):
        pressure = self.read()["pressure"]
        return 44330.0 * (1.0 - (pressure / sea_level_pa) ** (1.0 / 5.255))

    def print_reading(self):
        data = self.read()
        print(
            f"Temperature: {data['temperature']:.2f} °C, "
            f"Pressure: {data['pressure']/100:.2f} hPa, "
            f"Altitude: {data['altitude']:.2f} m"
        )

    def close(self):
        self.bus.close()
