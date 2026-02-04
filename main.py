try:
    import bootup
    bootup.bootup_sequence()
except ImportError:
    pass  # bootup module not found, skipping bootup sequence

import time
import numpy as np
import smbus2
import Adafruit_ADS1x15 as ADS1115
import adafruit_bmp as BMP180
import ENS160
import MQ_2_7_138 as MQS
import adafruit_sht31d as SHT31D
import pypms
import pyserial
import RPi.GPIO as GPIO