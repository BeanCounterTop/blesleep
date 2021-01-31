import sys, os, time
import logging
import struct
import binascii

from bytepatterns import miband4 as bytepattern

from bluepy.btle import (
    Peripheral, DefaultDelegate, 
    ADDR_TYPE_RANDOM, ADDR_TYPE_PUBLIC,
    BTLEException, BTLEDisconnectError
)
from datetime import datetime, timedelta
from Crypto.Cipher import AES
from datetime import datetime

from constants import (
    UUIDS, AUTH_STATES, ALERT_TYPES, QUEUE_TYPES, MUSICSTATE
)

from queue import Queue, Empty



class Delegate(DefaultDelegate):
    def __init__(self, device):
        DefaultDelegate.__init__(self)
        self.device = device
        self.pkg = 0

    def handleNotification(self, hnd, data):
        if hnd == self.device._char_auth.getHandle():
            if data[:3] == bytepattern.fetch_begin:
                self.device._req_rdn()
            elif data[:3] == bytepattern.fetch_error:
                self.device.state = AUTH_STATES.KEY_SENDING_FAILED
            elif data[:3] == bytepattern.fetch_continue:
                random_nr = data[3:]
                self.device._send_enc_rdn(random_nr)
            elif data[:3] == bytepattern.fetch_complete:
                self.device.state = AUTH_STATES.REQUEST_RN_ERROR
            elif data[:3] == bytepattern.auth_ok:
                self.device.state = AUTH_STATES.AUTH_OK
            else:
                self.device.state = AUTH_STATES.AUTH_FAILED
        elif hnd == self.device._char_heart_measure.getHandle():
            self.device.queue.put((QUEUE_TYPES.HEART, data))
        elif hnd == 0x38:
            if len(data) == 20 and struct.unpack('b', data[0:1])[0] == 1:
                self.device.queue.put((QUEUE_TYPES.RAW_ACCEL, data))
            elif len(data) == 16:
                self.device.queue.put((QUEUE_TYPES.RAW_HEART, data))
        elif hnd == self.device._char_hz.getHandle():
            if len(data) == 20 and struct.unpack('b', data[0:1])[0] == 1:
                self.device.queue.put((QUEUE_TYPES.RAW_ACCEL, data))
        else:
            print ("Unhandled handle: " + str(hnd) + " | Data: " + str(data))





class miband(Peripheral):
    def __init__(self, mac_address, key=None, timeout=0.5, debug=False):
        FORMAT = '%(asctime)-15s %(name)s (%(levelname)s) > %(message)s'
        logging.basicConfig(format=FORMAT)
        log_level = logging.WARNING if not debug else logging.DEBUG
        self._log = logging.getLogger(self.__class__.__name__)
        self._log.setLevel(log_level)

        self._log.info('Connecting to ' + mac_address)
        Peripheral.__init__(self, mac_address, addrType=ADDR_TYPE_PUBLIC)
        self._log.info('Connected')
        if not key:
            self.setSecurityLevel(level = "medium")

        self.timeout = timeout
        self.mac_address = mac_address
        self.state = None
        self.heart_measure_callback = None
        self.heart_raw_callback = None
        self.gyro_raw_callback = None
        self.auth_key = key
        self.queue = Queue()
        self.gyro_started_flag = False

        self.svc_1 = self.getServiceByUUID(UUIDS.SERVICE_MIBAND1)
        self.svc_2 = self.getServiceByUUID(UUIDS.SERVICE_MIBAND2)
        self.svc_heart = self.getServiceByUUID(UUIDS.SERVICE_HEART_RATE)
        self.svc_alert = self.getServiceByUUID(UUIDS.SERVICE_ALERT)

        self._char_alert = self.svc_alert.getCharacteristics(UUIDS.CHARACTERISTIC_ALERT)[0]

        self._char_auth = self.svc_2.getCharacteristics(UUIDS.CHARACTERISTIC_AUTH)[0]
        self._desc_auth = self._char_auth.getDescriptors(forUUID=UUIDS.NOTIFICATION_DESCRIPTOR)[0]

        self._char_heart_ctrl = self.svc_heart.getCharacteristics(UUIDS.CHARACTERISTIC_HEART_RATE_CONTROL)[0]
        self._char_heart_measure = self.svc_heart.getCharacteristics(UUIDS.CHARACTERISTIC_HEART_RATE_MEASURE)[0]
        self._heart_measure_handle = self._char_heart_measure.getHandle() + 1

        # Recorded information
        self._char_fetch = self.getCharacteristics(uuid=UUIDS.CHARACTERISTIC_FETCH)[0]
        self._desc_fetch = self._char_fetch.getDescriptors(forUUID=UUIDS.NOTIFICATION_DESCRIPTOR)[0]
        self._char_activity = self.getCharacteristics(uuid=UUIDS.CHARACTERISTIC_ACTIVITY_DATA)[0]
        self._desc_activity = self._char_activity.getDescriptors(forUUID=UUIDS.NOTIFICATION_DESCRIPTOR)[0]

        # Sensor characteristics and handles/descriptors
        self._char_hz = self.svc_1.getCharacteristics(UUIDS.CHARACTERISTIC_HZ)[0]
        self._hz_handle = self._char_hz.getHandle() + 1

        self._char_sensor = self.svc_1.getCharacteristics(UUIDS.CHARACTERISTIC_SENSOR)[0]
        self._sensor_handle = self._char_sensor.getHandle() + 1

        self._char_steps = self.svc_1.getCharacteristics(UUIDS.CHARACTERISTIC_STEPS)[0]
        self._steps_handle = self._char_steps.getHandle() + 1

        self._auth_notif(True)
        self.activity_notif_enabled = False
        self.waitForNotifications(0.1)
        self.setDelegate( Delegate(self) )

    def _auth_notif(self, enabled):
        if enabled:
            self._log.info("Enabling Auth Service notifications status...")
            self._desc_auth.write(bytepattern.start, True)
        elif not enabled:
            self._log.info("Disabling Auth Service notifications status...")
            self._desc_auth.write(bytepattern.stop, True)
        else:
            self._log.error("Something went wrong while changing the Auth Service notifications status...")

    def _auth_previews_data_notif(self, enabled):
        if enabled:
            self._log.info("Enabling Fetch Char notifications status...")
            self._desc_fetch.write(bytepattern.start, True)
            self._log.info("Enabling Activity Char notifications status...")
            self._desc_activity.write(bytepattern.start, True)
            self.activity_notif_enabled = True
        else:
            self._log.info("Disabling Fetch Char notifications status...")
            self._desc_fetch.write(bytepattern.stop, True)
            self._log.info("Disabling Activity Char notifications status...")
            self._desc_activity.write(bytepattern.stop, True)
            self.activity_notif_enabled = False

    def initialize(self):
        self._req_rdn()
        while True:
            self.waitForNotifications(0.1)
            if self.state == AUTH_STATES.AUTH_OK:
                self._log.info('Initialized')
                self._auth_notif(False)
                return True
            elif self.state is None:
                continue

            self._log.error(self.state)
            return False

    def _req_rdn(self):
        self._log.info("Requesting random number...")
        self._char_auth.write(bytepattern.request_random_number)
        self.waitForNotifications(self.timeout)

    def _send_enc_rdn(self, data):
        self._log.info("Sending encrypted random number")
        cmd = bytepattern.auth_key_prefix + self._encrypt(data)
        send_cmd = struct.pack('<18s', cmd)
        self._char_auth.write(send_cmd)
        self.waitForNotifications(self.timeout)

    def _encrypt(self, message):
        aes = AES.new(self.auth_key, AES.MODE_ECB)
        return aes.encrypt(message)

    def _get_from_queue(self, _type):
        try:
            res = self.queue.get(False)
        except Empty:
            return None
        if res[0] != _type:
            self.queue.put(res)
            return None
        return res[1]

    def _parse_queue(self):
        while True:
            try:
                res = self.queue.get(False)
                _type = res[0]
                if self.heart_measure_callback and _type == QUEUE_TYPES.HEART:
                    self.heart_measure_callback(self._parse_heart_measure(res[1]))
                elif self.gyro_raw_callback and _type == QUEUE_TYPES.RAW_ACCEL:
                    self.gyro_raw_callback(self._parse_raw_gyro(res[1]))
            except Empty:
                break

    def _parse_heart_measure(self, bytes):
        res = struct.unpack('bb', bytes)[1]
        return_tuple = ["HR", res]
        print("BPM: {}".format(res))
        return return_tuple

    def _parse_raw_gyro(self, bytes):
        res = []
        for i in range(3):
            g = struct.unpack('hhh', bytes[2 + i * 6:8 + i * 6])
            res.append({'x': g[0], 'y': g[1], 'z': g[2]})
        return_tuple = ["GYRO", res]
        return return_tuple

    def vibrate(self, ms):
        vibration_scaler = 0.75
        ms = min([round(ms / vibration_scaler), 255])
        sent_value = int(ms / 2)
        vibration_duration = ms / 1000
        self._char_alert.write(bytepattern.vibration(sent_value), withResponse=False)
        time.sleep(vibration_duration)

    def send_gyro_start(self, sensitivity):
        if not self.gyro_started_flag:
            self._log.info("Starting gyro...")
            self.writeCharacteristic(self._sensor_handle, bytepattern.start, withResponse=True)
            self.writeCharacteristic(self._steps_handle, bytepattern.start, withResponse=True)
            self.writeCharacteristic(self._hz_handle, bytepattern.start, withResponse=True)
            self.gyro_started_flag = True
            
        self._char_sensor.write(bytepattern.gyro_start(sensitivity), withResponse=False)
        self.writeCharacteristic(self._sensor_handle, bytepattern.stop, withResponse=True)
        self._char_sensor.write(b'\x02', withResponse=False)

    def send_heart_measure_start(self):
        self._log.info("Starting heart measure...")
        self._char_heart_ctrl.write(bytepattern.stop_heart_measure_manual, True)
        self._char_heart_ctrl.write(bytepattern.stop_heart_measure_continues, True)
        self.writeCharacteristic(self._heart_measure_handle, bytepattern.start, withResponse=True)
        self._char_heart_ctrl.write(bytepattern.start_heart_measure_continues, True)
        
    def send_heart_measure_keepalive(self):
        self._char_heart_ctrl.write(bytepattern.heart_measure_keepalive, True)

    def start_heart_and_gyro(self, sensitivity, callback):
        self.heart_measure_callback = callback
        self.gyro_raw_callback = callback

        self.send_gyro_start(sensitivity)
        self.send_heart_measure_start()

        heartbeat_time = time.time()
        while True:
            self.waitForNotifications(0.5)
            self._parse_queue()
            if (time.time() - heartbeat_time) >= 12:
                heartbeat_time = time.time()
                self.send_heart_measure_keepalive()
                self.send_gyro_start(sensitivity)