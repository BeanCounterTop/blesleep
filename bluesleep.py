#!/usr/bin/env python3

from bluepy import btle
from bluepy.btle import BTLEDisconnectError

from miband import miband
import sleepdata

import threading
import re

import subprocess
import time
from datetime import datetime

auth_key_filename = 'auth_key.txt'
mac_filename = 'mac.txt'
csv_filename = "sleep_data.csv"

band = None

#-------------------------------------------------------------------------#

class regex_patterns():
    mac_regex_pattern = re.compile(r'([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})')
    authkey_regex_pattern = re.compile(r'([0-9a-fA-F]){32}')


def get_mac_address(filename):
    try:
        with open(filename, "r") as f:
            hwaddr_search = re.search(regex_patterns.mac_regex_pattern, f.read().strip())
            if hwaddr_search:
                MAC_ADDR = hwaddr_search[0]
            else:
                print ("No valid MAC address found in {}".format(filename))
                exit(1)
    except FileNotFoundError:
            print ("MAC file not found: {}".format(filename))
            exit(1)
    return MAC_ADDR


def get_auth_key(filename):
    try:
        with open(filename, "r") as f:
            key_search = re.search(regex_patterns.authkey_regex_pattern, f.read().strip())
            if key_search:
                AUTH_KEY = bytes.fromhex(key_search[0])
            else:
                print ("No valid auth key found in {}".format(filename))
                exit(1)
    except FileNotFoundError:
            print ("Auth key file not found: {}".format(filename))
            exit(1)
    return AUTH_KEY

def process_data(data, tick_time):
    if data[0] == "GYRO":
        sleepdata.process_gyro_data(data[1], tick_time)
    elif data[0] == "HR":
        sleepdata.process_heartrate_data(data[1], tick_time)

def sleep_monitor_callback(data):
    tick_time = time.time()
    if not sleepdata.last_tick_time:
        sleepdata.last_tick_time = time.time()
    
    process_data(data, tick_time)

    if (tick_time - sleepdata.last_tick_time) >= sleepdata.tick_seconds:
        sleepdata.average_raw_data(tick_time)
        sleepdata.last_tick_time = time.time()

def connect(mac_filename, auth_key_filename):
    global band
    success = False
    timeout = 3
    msg = 'Connection to the band failed. Trying again in {} seconds'

    MAC_ADDR = get_mac_address(mac_filename)
    AUTH_KEY = get_auth_key(auth_key_filename)

    while not success:
        try:
            band = miband(MAC_ADDR, AUTH_KEY, debug=True)
            success = band.initialize()
        except BTLEDisconnectError:
            print(msg.format(timeout))
            time.sleep(timeout)
        except KeyboardInterrupt:
            print("\nExit.")
            exit()

def start_data_pull():
    while True:
        try:
            band.start_heart_and_gyro(sensitivity=1, callback=sleep_monitor_callback)
        except BTLEDisconnectError:
            band.gyro_started_flag = False
            connect()

def vibrate_pattern(duration):
    print("Sending vibration...")
    duration_start = time.time()
    pulse_pattern = [[30, 0.01], [60, 0.01], [90, 0.01], [120, 0.01], [150, 0.01], [180, 0.01]]

    while True:
        if (time.time() - duration_start) >= duration:
            print ("Stopping vibration")
            band.vibrate(0)
            break
        else:
            for pattern in pulse_pattern:
                if (time.time() - duration_start) >= duration:
                    break
                vibrate_ms = pattern[0]
                vibro_delay = pattern[1]
                band.vibrate(vibrate_ms)
                time.sleep(vibro_delay)

def vibrate_rolling():
    print("Sending rolling vibration...")
    for x in range(10):
        for x in range(20, 40, 1):
            band.vibrate(x)
        for x in range(40, 20, -1):
            band.vibrate(x)

if __name__ == "__main__":
    connect(mac_filename, auth_key_filename)
    #vibrate_pattern(10)
    data_gather_thread = threading.Thread(target=start_data_pull)
    data_gather_thread.start()
    sleepdata.init_graph()



#import simpleaudio as sa
# comfort_wav = 'comfort.wav'
# wave_obj = sa.WaveObject.from_wave_file(comfort_wav)
# comfort_delay = 30
# comfort_lasttime = time.time()
