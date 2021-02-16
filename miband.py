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
    UUIDS, AUTH_STATES, QUEUE_TYPES, BYTEPATTERNS
)

from queue import Queue, Empty



class Delegate(DefaultDelegate):
    def __init__(self, device):
        DefaultDelegate.__init__(self)
        self.device = device
        self.pkg = 0

    def handleNotification(self, hnd, data):
        if hnd == self.device._char_auth.getHandle():
            if data[:3] == BYTEPATTERNS.fetch_begin:
                self.device._req_rdn()
            elif data[:3] == BYTEPATTERNS.fetch_error:
                self.device.state = AUTH_STATES.KEY_SENDING_FAILED
            elif data[:3] == BYTEPATTERNS.fetch_continue:
                random_nr = data[3:]
                self.device._send_enc_rdn(random_nr)
            elif data[:3] == BYTEPATTERNS.fetch_complete:
                self.device.state = AUTH_STATES.REQUEST_RN_ERROR
            elif data[:3] == BYTEPATTERNS.auth_ok:
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
            else:
                print("Unhandled data on handle 0x38: {}".format(data))
        elif hnd == self.device._char_hz.getHandle():
            if len(data) == 20 and struct.unpack('b', data[0:1])[0] == 1:
                self.device.queue.put((QUEUE_TYPES.RAW_GYRO, data))
            elif len(data) == 11:
                #print("Unknown data: {}".format(bytes.hex(data, " ")))
                #print(struct.unpack('BBBBBBBBBB', data[1:]))
                # Seems to be a counter of the time the gyro is enabled.
                #print(struct.unpack(">x2L", data))
                #print(struct.unpack("<x5H", data))
                ...
            elif len(data) == 8:
                self.device.queue.put((QUEUE_TYPES.AVG_GYRO, data))
            else:
                #print("Unknown sensor data ({}): {}".format(len(data), bytes.hex(data, " ")))
                ...
        else:
            #print ("Unhandled handle: " + str(hnd) + " | Data: " + bytes.hex(data, " "))
            ...


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
        self.gyro_avg_callback = None
        self.auth_key = key
        self.queue = Queue()
        self.write_queue = Queue()
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
            self._desc_auth.write(BYTEPATTERNS.start, True)
        elif not enabled:
            self._log.info("Disabling Auth Service notifications status...")
            self._desc_auth.write(BYTEPATTERNS.stop, True)
        else:
            self._log.error("Something went wrong while changing the Auth Service notifications status...")


    def _auth_previews_data_notif(self, enabled):
        if enabled:
            self._log.info("Enabling Fetch Char notifications status...")
            self._desc_fetch.write(BYTEPATTERNS.start, True)
            self._log.info("Enabling Activity Char notifications status...")
            self._desc_activity.write(BYTEPATTERNS.start, True)
            self.activity_notif_enabled = True
        else:
            self._log.info("Disabling Fetch Char notifications status...")
            self._desc_fetch.write(BYTEPATTERNS.stop, True)
            self._log.info("Disabling Activity Char notifications status...")
            self._desc_activity.write(BYTEPATTERNS.stop, True)
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
        self._char_auth.write(BYTEPATTERNS.request_random_number)
        self.waitForNotifications(self.timeout)


    def _send_enc_rdn(self, data):
        self._log.info("Sending encrypted random number")
        cmd = BYTEPATTERNS.auth_key_prefix + self._encrypt(data)
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
                queue_data = self.queue.get(False)
                _type = queue_data[0]
                if self.heart_measure_callback and _type == QUEUE_TYPES.HEART:
                    self.heart_measure_callback(self._parse_heart_measure(queue_data[1]))
                elif self.gyro_raw_callback and _type == QUEUE_TYPES.RAW_GYRO:
                    self.gyro_raw_callback(self._parse_raw_gyro(queue_data[1]))
                elif self.gyro_avg_callback and _type == QUEUE_TYPES.AVG_GYRO:
                    self.gyro_avg_callback(self._parse_avg_gyro(queue_data[1]))
            except Empty:
                break

    def _parse_avg_gyro(self, bytes):
        gyro_avg_data = struct.unpack('<b3h', bytes[1:])
        gyro_dict = {
            'gyro_time': gyro_avg_data[0],
            'gyro_avg_x': gyro_avg_data[1],
            'gyro_avg_y': gyro_avg_data[2],
            'gyro_avg_z': gyro_avg_data[3]
        }
        return_tuple = ['GYRO_AVG', gyro_dict]
        return return_tuple


    def _parse_heart_measure(self, bytes):
        res = struct.unpack('bb', bytes)[1]
        return_tuple = ["HR", res]
        #print("BPM: {}".format(res))
        return return_tuple


    def _parse_raw_gyro(self, bytes):
        gyro_raw_data_list = []
        for i in range(2, 20, 6):
            gyro_raw_data = struct.unpack("3h", bytes[i:(i+6)])
            gyro_dict = {
                'gyro_raw_x': gyro_raw_data[0],
                'gyro_raw_y': gyro_raw_data[1],
                'gyro_raw_z': gyro_raw_data[2]
            }
            gyro_raw_data_list.append(gyro_dict)
        return_tuple = ["GYRO_RAW", gyro_raw_data_list]
        return return_tuple


    def process_write_queue(self):
        while True:
            try:
                res = self.write_queue.get(False)
                _type = res[0]
                _payload = res[1]
                if _type == 'write_cmd':
                    self.write_cmd(_payload[0], _payload[1], response=_payload[2])
                elif _type == 'write_req':
                    self.write_req(_payload[0], _payload[1], response=_payload[2])
            except Empty:
                break


    def vibrate(self, value):
        if value == 255 or value == 0:
            # '255' means 'continuous vibration' 
            #   I've arbitrarily assigned the otherwise pointless value of '0' to indicate 'stop_vibration'
            #   These modes do not require pulse timing to avoid strange behavior.
            self.write_cmd(self._char_alert, BYTEPATTERNS.vibration(value), queued=True)
        else:
            # A value of '150' will vibrate for ~200ms, hence vibration_scaler.
            #   This isn't exact however, but does leave a ~5ms gap between pulses.
            #   A scaler any lower causes the pulses to be indistinguishable from each other to a human.
            #   I considered making this function accept a desired amount of vibration time in ms, 
            #   however it was fiddly and I couldn't get it right.  More work could be done here.
            vibration_scaler = 0.75  
            ms = round(value / vibration_scaler)
            vibration_duration = ms / 1000
            self.write_cmd(self._char_alert, BYTEPATTERNS.vibration(value), queued=True)
            time.sleep(vibration_duration)


    def write_cmd(self, characteristic, data, response=False, queued=False):
        if queued:
            self.write_queue.put(['write_cmd', [characteristic, data, response]])
        else:
            characteristic.write(data, withResponse=response)


    def write_req(self, handle, data, response=True, queued=False):
        if queued:
            self.write_queue.put(['write_req', [handle, data, response]])
        else:
            self.writeCharacteristic(handle, data, withResponse=response)


    def wait_for_notifications_with_queued_writes(self, wait):
        self.process_write_queue()
        self.waitForNotifications(wait)


    def send_gyro_start(self, sensitivity):
        if not self.gyro_started_flag:
            self._log.info("Starting gyro...")
            self.write_req(self._sensor_handle, BYTEPATTERNS.start)
            self.write_req(self._steps_handle, BYTEPATTERNS.start)
            self.write_req(self._hz_handle, BYTEPATTERNS.start)
            self.gyro_started_flag = True
        self.write_cmd(self._char_sensor, BYTEPATTERNS.gyro_start(sensitivity))
        self.write_req(self._sensor_handle, BYTEPATTERNS.stop)
        self.write_cmd(self._char_sensor, b'\x02')


    def send_heart_measure_start(self):
        self._log.info("Starting heart measure...")
        self.write_cmd(self._char_heart_ctrl, BYTEPATTERNS.stop_heart_measure_manual, response=True)
        self.write_cmd(self._char_heart_ctrl, BYTEPATTERNS.stop_heart_measure_continues, response=True)
        self.write_req(self._heart_measure_handle, BYTEPATTERNS.start)
        self.write_cmd(self._char_heart_ctrl, BYTEPATTERNS.start_heart_measure_continues, response=True)


    def send_heart_measure_keepalive(self):
        self.write_cmd(self._char_heart_ctrl, BYTEPATTERNS.heart_measure_keepalive, response=True)


    def start_heart_and_gyro(self, sensitivity, callback):
        self.heart_measure_callback = callback
        self.gyro_raw_callback = callback

        self.send_gyro_start(sensitivity)
        self.send_heart_measure_start()

        heartbeat_time = time.time()
        while True:
            self.wait_for_notifications_with_queued_writes(0.5)
            self._parse_queue()
            if (time.time() - heartbeat_time) >= 12:
                heartbeat_time = time.time()
                self.send_heart_measure_keepalive()
                self.send_gyro_start(sensitivity)