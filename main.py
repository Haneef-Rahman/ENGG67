try:
    import bootup
    bootup.bootup_sequence()
except ImportError:
    pass  # bootup module not found, skipping bootup sequence

import time
import numpy as np
import smbus2
import Adafruit_ADS1x15
import adafruit_bmp
import ENS160
import MQ_2_7_138
import adafruit_sht31d
import pypms
import serial