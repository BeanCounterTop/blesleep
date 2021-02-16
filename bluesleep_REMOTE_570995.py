#!/usr/bin/env python3

import time, re, threading
from bluepy.btle import BTLEDisconnectError
from miband import miband
import sleepdata
from vibrate import Vibrate




auth_key_filename = 'auth_key.txt'
mac_filename = 'mac.txt'

maximize_graph = False

vibration_settings = {
    'interval_minutes': 20,
    'duration_seconds': 10,
    'type': 'random',
    'heartrate_alarm_pct': 17
    }

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


def average_data(tick_time):
    if (tick_time - sleepdata.last_tick_time) >= sleepdata.tick_seconds:
        sleepdata.average_raw_data(tick_time)
        sleepdata.last_tick_time = time.time()

   
def sleep_monitor_callback(data):
    tick_time = time.time()

    if not sleepdata.last_tick_time:
        sleepdata.last_tick_time = time.time()

    if data[0] == "GYRO_RAW":
        sleepdata.process_gyro_data(data[1], tick_time)
    elif data[0] == "HR":
        sleepdata.process_heartrate_data(data[1], tick_time)

    average_data(tick_time)

    vibration.heartrate_increase_pct = sleepdata.analyze_heartrate(10)
    print("HR increase percent: {}".format(vibration.heartrate_increase_pct))


def connect():
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


def start_vibration():
    while True:
        try:
            #vibration.timed_vibration(vibration_settings)
            vibration.heartrate_alarm(vibration_settings)

        except BTLEDisconnectError:
            print("Vibration thread waiting for band reconnect...")
            time.sleep(1)


if __name__ == "__main__":
    connect()
    vibration = Vibrate(band)
    threading.Thread(target=start_data_pull).start()
    threading.Thread(target=start_vibration).start()
    sleepdata.init_graph(maximize=maximize_graph, graph_displaytime_mins=5)



#import simpleaudio as sa
# comfort_wav = 'comfort.wav'
# wave_obj = sa.WaveObject.from_wave_file(comfort_wav)
# comfort_delay = 30
# comfort_lasttime = time.time()
