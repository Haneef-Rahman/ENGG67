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
import pigio
import buzzer
import LED_control

def hw_handle_data():
    state = analyze_data()
    if state == 0: pass

class hardware:
    def __init__(self):
        self.state = 1

    def __analyze_data(self,data):
        #placeholder conditions
        if "nominal":
            next_state = 1
        elif "suboptimal":
            next_state = 2
        else:
            next_state = 3

        return next_state
    
    def handle_data(self,data):
        next_state = self.__analyze_data(data)
        if next_state == self.state:
            return 0
        else:
            #do things. change LED etc
            pass

def main():
    #bootup
    all_fans_init()
    buzzer_ini()
    led_init()

    log_file = "log.txt"
    log = open(log_file,"a",encoding="UTF-8")

    vent_fans_start()
    while True:
        try: 
            sensor_fan_start()

            time.sleep(10)
            data = take_readings()

            hw_handle_data(data)
            log.write(data)

        except KeyboardInterrupt:
            break

    log.close()

        

    