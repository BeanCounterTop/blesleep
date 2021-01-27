#!/usr/bin/env python3

from bluepy import btle
from bluepy.btle import BTLEDisconnectError

from miband import miband

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import csv
import random
from os import path

import threading
import re

import subprocess
import time
from datetime import datetime

sleep_data = { 
                'heartrate': {
                    'value_name': 'bpm',
                    'periods': [2, 5, 10, 15], 
                    'raw_data': [],
                    'averaged_data': [],
                    },
                'movement':{
                    'value_name': 'movement',
                    'periods': [10, 30, 60],
                    'raw_data': [],
                    'averaged_data': [],
                    'workspace': {
                        'gyro_last_x' : 0,
                        'gyro_last_y' : 0,
                        'gyro_last_z' : 0
                    }
                } 
            }

auth_key_filename = 'auth_key.txt'
mac_filename = 'mac.txt'
csv_filename = "sleep_data.csv"

plt.style.use('dark_background')
graph_figure = plt.figure()
graph_axes = graph_figure.add_subplot(1, 1, 1)
graph_data = {}

last_heartrate = 0
last_tick_time = None
tick_seconds = 0.5

fieldnames = ['time']
for data_type in sleep_data:
    periods = sleep_data[data_type]['periods']
    for period in periods:
        fieldnames.append(data_type + str(period))


#-------------------------------------------------------------------------#


def write_csv(data):
    global fieldnames
    global csv_filename
    if not path.exists(csv_filename):
        with open(csv_filename, 'w', newline='') as csvfile:
            csv_writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            csv_writer.writeheader() 
            csv_writer.writerow(data)
    else:
        with open(csv_filename, 'a', newline='') as csvfile:
            csv_writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            csv_writer.writerow(data)


def get_mac_address(filename):
    mac_regex_pattern = re.compile(r'([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})')
    try:
        with open(filename, "r") as f:
            hwaddr_search = re.search(mac_regex_pattern, f.read().strip())

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
    authkey_regex_pattern = re.compile(r'([0-9a-fA-F]){32}')
    try:
        with open(filename, "r") as f:
            key_search = re.search(authkey_regex_pattern, f.read().strip())
            if key_search:
                AUTH_KEY = bytes.fromhex(key_search[0])
            else:
                print ("No valid auth key found in {}".format(filename))
                exit(1)
    except FileNotFoundError:
            print ("Auth key file not found: {}".format(filename))
            exit(1)
    return AUTH_KEY


def process_heartrate_data(heartrate_data, tick_time):
    print("BPM: " + str(heartrate_data))
    if heartrate_data > 0:
        value_name = sleep_data['heartrate']['value_name']
        sleep_data['heartrate']['raw_data'].append({
            'time': tick_time,
            value_name: heartrate_data
        } )


def process_gyro_data(gyro_data, tick_time):
    # Each gyro reading from miband4 comes over as a group of three,
    #     each containing x,y,z values.  This function summarizes the
    #     values into a single consolidated movement value.

    global sleep_data

    sleep_move = sleep_data['movement']
    sleep_workspace = sleep_move['workspace']

    gyro_last_x = sleep_workspace['gyro_last_x']
    gyro_last_y = sleep_workspace['gyro_last_y']
    gyro_last_z = sleep_workspace['gyro_last_z']
    value_name = sleep_move['value_name']
    gyro_movement = 0
    for gyro_datum in gyro_data:
        gyro_delta_x = abs(gyro_datum['x'] - gyro_last_x)
        gyro_last_x = gyro_datum['x']
        gyro_delta_y = abs(gyro_datum['y'] - gyro_last_y)
        gyro_last_y = gyro_datum['y']
        gyro_delta_z = abs(gyro_datum['z'] - gyro_last_z)
        gyro_last_z = gyro_datum['z']
        gyro_delta_sum = gyro_delta_x + gyro_delta_y + gyro_delta_z
        gyro_movement += gyro_delta_sum

    sleep_workspace['gyro_last_x'] = gyro_last_x
    sleep_workspace['gyro_last_y'] = gyro_last_y
    sleep_workspace['gyro_last_z'] = gyro_last_z

    sleep_move['raw_data'].append({
        'time': tick_time,
        value_name: gyro_movement
    })


def flush_old_raw_data(tick_time):
    global sleep_data
    
    for data_type in sleep_data:
        s_data = sleep_data[data_type]
        periods = s_data['periods']

        cleaned_raw_data = []
        
        for raw_datum in s_data['raw_data']:
            datum_age = tick_time - raw_datum['time']
            if datum_age < max(periods):
                cleaned_raw_data.append(raw_datum)

        s_data['raw_data'] = cleaned_raw_data


def average_raw_data(tick_time):
    global sleep_data
    global last_heartrate
    timestamp = datetime.fromtimestamp(tick_time)
    csv_out = {'time': timestamp }

    for data_type in sleep_data:
        s_data = sleep_data[data_type]
        period_averages_dict = {'time': timestamp}
        periods = s_data['periods']
        value_name = s_data['value_name']

        flush_old_raw_data(tick_time)

        for period_seconds in periods:
            period_data = []
            period_averages_dict[period_seconds] = 0
            for raw_datum in s_data['raw_data']:
                datum_age_seconds = tick_time - raw_datum['time']
                if datum_age_seconds < period_seconds:
                    period_data.append(raw_datum[value_name])
                    
            if len(period_data) > 0:
                period_data_average = sum(period_data) / len(period_data)
            else:
                print("({}) Period data empty: {}".format(data_type,
                                                          period_seconds))
                if data_type == "heartrate" and period_seconds == min(periods):
                    period_data_average = last_heartrate
                else:
                    period_data_average = 0

            period_averages_dict[period_seconds] = zero_to_nan(period_data_average)

            csv_out[data_type + str(period_seconds)] = zero_to_nan(period_data_average)

        s_data['averaged_data'].append(period_averages_dict)
    write_csv(csv_out)


def zero_to_nan(value):
    if value == 0:
        return (float('nan'))
    return int(value)


def sleep_monitor_callback(data):
    global sleep_data
    global last_tick_time

    tick_time = time.time()
    if not last_tick_time:
        last_tick_time = time.time()
    
    if data[0] == "GYRO":
        process_gyro_data(data[1], tick_time)
    elif data[0] == "HR":
        process_heartrate_data(data[1], tick_time)

    if (tick_time - last_tick_time) >= tick_seconds:
        average_raw_data(tick_time)
        last_tick_time = time.time()


def init_graph_data():
    for data_type in sleep_data:
        data_periods = sleep_data[data_type]['periods']
        graph_data[data_type] = {
            'time': [],
            'data': {}
        }
        for period in data_periods:
            graph_data[data_type]['data'][period] = []


def update_graph_data():
    global sleep_data
    global graph_data

    for data_type in sleep_data:
        s_data = sleep_data[data_type]  # Re-referenced to shorten name
        avg_data = s_data['averaged_data']

        if len(avg_data) > 1:
            
            g_data = graph_data[data_type]  # Re-referenced to short name
            data_periods = s_data['periods']

            starting_index = max([(len(g_data['time']) - 1), 0])
            ending_index = len(avg_data) - 1

            # Re-referenced to shorten name
            sleep_data_range = avg_data[starting_index:ending_index]

            for sleep_datum in sleep_data_range:
                g_data['time'].append(sleep_datum['time'])
                for period in data_periods:
                    if g_data['data'][period] != 'nan':
                        g_data['data'][period].append(sleep_datum[period])


def graph_animation(i):
    global sleep_data
    global graph_axes
    global graph_data
    plotflag = False

    if len(graph_data) == 0:
        init_graph_data()

    update_graph_data()

    for data_type in graph_data:
        if len(graph_data[data_type]['time']) > 0:
            graph_axes.clear()
            break

    for data_type in sleep_data:
        s_data = sleep_data[data_type]
        g_data = graph_data[data_type]
        if len(g_data['time']) > 0:
            plotflag = True
            data_periods = sleep_data[data_type]['periods']
            for period in data_periods:
                axis_label = "{} {} sec".format(s_data['value_name'], period)
                graph_axes.plot(g_data['time'],
                                g_data['data'][period],
                                label=axis_label) 

    if plotflag:
        plt.legend()


def connect():
    global band
    global mac_filename
    global auth_key_filename

    success = False
    timeout = 3
    msg = 'Connection to the MIBand failed. Trying again in {} seconds'

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
    global band

    while True:
        try:
            band.start_heart_and_gyro(callback=sleep_monitor_callback)
        except BTLEDisconnectError:
            band.gyro_started_flag = False
            connect()


if __name__ == "__main__":
    connect()
    data_gather_thread = threading.Thread(target=start_data_pull)
    data_gather_thread.start()
    ani = animation.FuncAnimation(graph_figure, graph_animation, interval=1000)
    plt.show()


#import simpleaudio as sa
# comfort_wav = 'comfort.wav'
# wave_obj = sa.WaveObject.from_wave_file(comfort_wav)
# comfort_delay = 30
# comfort_lasttime = time.time()
