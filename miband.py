import sys, os, time
import logging
import struct

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

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty
try:
    xrange
except NameError:
    xrange = range


class Delegate(DefaultDelegate):
    def __init__(self, device):
        DefaultDelegate.__init__(self)
        self.device = device
        self.pkg = 0

    def handleNotification(self, hnd, data):
        if hnd == self.device._char_auth.getHandle():
            if data[:3] == b'\x10\x01\x01':
                self.device._req_rdn()
            elif data[:3] == b'\x10\x01\x04':
                self.device.state = AUTH_STATES.KEY_SENDING_FAILED
            elif data[:3] == b'\x10\x02\x01':
                # 16 bytes
                random_nr = data[3:]
                self.device._send_enc_rdn(random_nr)
            elif data[:3] == b'\x10\x02\x04':
                self.device.state = AUTH_STATES.REQUEST_RN_ERROR
            elif data[:3] == b'\x10\x03\x01':
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
        # The fetch characteristic controls the communication with the activity characteristic.
        elif hnd == self.device._char_fetch.getHandle():
            if data[:3] == b'\x10\x01\x01':
                # get timestamp from what date the data actually is received
                year = struct.unpack("<H", data[7:9])[0]
                month = struct.unpack("b", data[9:10])[0]
                day = struct.unpack("b", data[10:11])[0]
                hour = struct.unpack("b", data[11:12])[0]
                minute = struct.unpack("b", data[12:13])[0]
                self.device.first_timestamp = datetime(year, month, day, hour, minute)
                print("Fetch data from {}-{}-{} {}:{}".format(year, month, day, hour, minute))
                self.pkg = 0 #reset the packing index
                self.device._char_fetch.write(b'\x02', False)
            elif data[:3] == b'\x10\x02\x01':
                if self.device.last_timestamp > self.device.end_timestamp - timedelta(minutes=1):
                    print("Finished fetching")
                    return
                print("Trigger more communication")
                time.sleep(1)
                t = self.device.last_timestamp + timedelta(minutes=1)
                self.device.start_get_previews_data(t)

            elif data[:3] == b'\x10\x02\x04':
                print("No more activity fetch possible")
                return
            else:
                print("Unexpected data on handle " + str(hnd) + ": " + str(data))
                return
        elif hnd == self.device._char_activity.getHandle():
            if len(data) % 4 == 1:
                self.pkg += 1
                i = 1
                while i < len(data):
                    index = int(self.pkg) * 4 + (i - 1) / 4
                    timestamp = self.device.first_timestamp + timedelta(minutes=index)
                    self.device.last_timestamp = timestamp
                    category = struct.unpack("<B", data[i:i + 1])[0]
                    intensity = struct.unpack("B", data[i + 1:i + 2])[0]
                    steps = struct.unpack("B", data[i + 2:i + 3])[0]
                    heart_rate = struct.unpack("B", data[i + 3:i + 4])[0]
                    if timestamp < self.device.end_timestamp:
                        self.device.activity_callback(timestamp,category,intensity,steps,heart_rate)
                    i += 4
        elif hnd == self.device._char_hz.getHandle():
            if len(data) == 20 and struct.unpack('b', data[0:1])[0] == 1:
                self.device.queue.put((QUEUE_TYPES.RAW_ACCEL, data))
        else:
            print ("Unhandled handle: " + str(hnd) + " | Data: " + str(data))


class miband(Peripheral):
    _send_rnd_cmd = struct.pack('<2s', b'\x02\x00')
    _send_enc_key = struct.pack('<2s', b'\x03\x00')
    def __init__(self, mac_address,key=None, timeout=0.5, debug=False):
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

        self.start_bytes = b'\x01\x00'
        self.stop_bytes = b"\x00\x00"
        self.gyro_sensitivity = 1

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

    def generateAuthKey(self):
        if(self.auth_key):
            return struct.pack('<18s',b'\x01\x00'+ self.auth_key)

    def _auth_notif(self, enabled):
        if enabled:
            self._log.info("Enabling Auth Service notifications status...")
            self._desc_auth.write(self.start_bytes, True)
        elif not enabled:
            self._log.info("Disabling Auth Service notifications status...")
            self._desc_auth.write(self.stop_bytes, True)
        else:
            self._log.error("Something went wrong while changing the Auth Service notifications status...")

    def _auth_previews_data_notif(self, enabled):
        if enabled:
            self._log.info("Enabling Fetch Char notifications status...")
            self._desc_fetch.write(self.start_bytes, True)
            self._log.info("Enabling Activity Char notifications status...")
            self._desc_activity.write(self.start_bytes, True)
            self.activity_notif_enabled = True
        else:
            self._log.info("Disabling Fetch Char notifications status...")
            self._desc_fetch.write(self.stop_bytes, True)
            self._log.info("Disabling Activity Char notifications status...")
            self._desc_activity.write(self.stop_bytes, True)
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
        self._char_auth.write(self._send_rnd_cmd)
        self.waitForNotifications(self.timeout)

    def _send_enc_rdn(self, data):
        self._log.info("Sending encrypted random number")
        cmd = self._send_enc_key + self._encrypt(data)
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
        return return_tuple

    def _parse_raw_gyro(self, bytes):
        res = []
        for i in xrange(3):
            g = struct.unpack('hhh', bytes[2 + i * 6:8 + i * 6])
            res.append({'x': g[0], 'y': g[1], 'z': g[2]})
        return_tuple = ["GYRO", res]
        return return_tuple

    def send_vibration(self, duration):
        duration_time = time.time()
        pulse_time = time.time()
        vibro_start_value = 30
        #pulse_value = 100
        duration = 20
        vibro_current_value = vibro_start_value
        
        while True:
            if (time.time() - duration_time) >= duration:
                print ("Stopping vibration")
                self._char_alert.write(b'\x00\x00\x00\x00\x00\x00', withResponse=False)
                break
            else:
                if ((time.time() - pulse_time)*1000) >= vibro_current_value:
                    pulse_time = time.time()
                    self._char_alert.write(b'\xff' + (vibro_current_value).to_bytes(1, 'big') + b'\x00\x00\x00\x01', withResponse=False)
                    vibro_current_value += 1
                    print (vibro_current_value)
                    if vibro_current_value > 255:
                        vibro_current_value = vibro_start_value

    def send_gyro_start(self):
        if not self.gyro_started_flag:
            self._log.info("Starting gyro...")
            self.writeCharacteristic(self._sensor_handle, self.start_bytes, withResponse=True)
            self.writeCharacteristic(self._steps_handle, self.start_bytes, withResponse=True)
            self.writeCharacteristic(self._hz_handle, self.start_bytes, withResponse=True)
            self.gyro_started_flag = True
            
        self._char_sensor.write(b'\x01' + bytes([self.gyro_sensitivity]) + b'\x19', withResponse=False)
        self.writeCharacteristic(self._sensor_handle, self.stop_bytes, withResponse=True)
        self._char_sensor.write(b'\x02', withResponse=False)

    def send_heart_measure_start(self):
        self._log.info("Starting heart measure...")
        # stop heart monitor continues & manual
        self._char_heart_ctrl.write(b'\x15\x02\x00', True)
        self._char_heart_ctrl.write(b'\x15\x01\x00', True)
        # enable heart monitor notifications
        self.writeCharacteristic(self._heart_measure_handle, self.start_bytes, withResponse=True)
        # start heart monitor continues
        self._char_heart_ctrl.write(b'\x15\x01\x01', True)
        
    def send_heart_measure_keepalive(self):
        self._char_heart_ctrl.write(b'\x16', True)

    def start_heart_and_gyro(self, callback):
        self.heart_measure_callback = callback
        self.gyro_raw_callback = callback

        self.send_gyro_start()
        self.send_heart_measure_start()

        heartbeat_time = time.time()
        while True:
            self.waitForNotifications(0.5)
            self._parse_queue()
            if (time.time() - heartbeat_time) >= 12:
                heartbeat_time = time.time()
                self.send_heart_measure_keepalive()
                self.send_gyro_start()