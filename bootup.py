import subprocess
import sys

def bootup_sequence():
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "time"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "smbus2"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Adafruit_ADS1x15"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "adafruit-python-bmp"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "git+https://github.com/Haneef-Rahman/ENS160.git"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "git+https://github.com/Haneef-Rahman/MQ-2-7-138.git"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "adafruit-circuitpython-sht31d"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pypms"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyserial"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "RPi.GPIO"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pigpio"])
    except:
        pass  # Library already installed