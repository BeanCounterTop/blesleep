import time
import random
import logging

# Notes:
# The miband4 does not (seem to) support different vibration intensities, rather the values sent (2-255)
# represent how long the vibration motor runs.  A value of 30 roughly corresponds to 60ms of motor run time.
# Sending a value of 255 triggecd rs continuous vibration.
# Currently "continuous" mode doesn't work, as it doesn't turn off.
# This will be fixed shortly.

class Vibrate():
    vibrate_band = None
    vibration_log = None
    heartrate_increase_pct = 0


    def __init__(self, band):
        self.vibrate_band = band

        FORMAT = '%(asctime)-15s %(name)s (%(levelname)s) > %(message)s'
        logging.basicConfig(format=FORMAT)
        vibration_log_level = logging.INFO
        self.vibration_log = logging.getLogger(__name__)
        self.vibration_log.setLevel(vibration_log_level)


    def heartrate_alarm(self, settings):
        interval_minutes = settings['interval_minutes']
        duration_seconds = settings['duration_seconds']
        vibration_type = settings['type']
        heartrate_alarm_pct = settings['heartrate_alarm_pct']

        tick_time = time.time()
        buzz_delay = interval_minutes * 60
        buzz_timer = tick_time - buzz_delay


        self.vibration_log.info("Starting heartrate alarm timer, alarming at {} percent for {} seconds with a {} minute interval".format(
                                                                                                        heartrate_alarm_pct, 
                                                                                                        duration_seconds, 
                                                                                                        interval_minutes))
        if vibration_type not in ['random', 'pattern', 'rolling', 'continuous']:
            self.vibration_log.warn("Invalid or no vibration type specified: {}".format(type))
            self.vibration_log.warn("Must be one of these: random, pattern, rolling, continuous")
            return

        while True:
            elapsed_time = tick_time - buzz_timer
            if elapsed_time >= buzz_delay and self.heartrate_increase_pct >= heartrate_alarm_pct:
                self.vibration_log.info("Heartrate alarm triggered at {} percent, buzzing".format(self.heartrate_increase_pct))
                if vibration_type == 'random':
                    self.vibrate_random(duration_seconds)
                elif vibration_type == 'pattern':
                    self.vibrate_pattern(duration_seconds)
                elif vibration_type == 'rolling':
                    self.vibrate_rolling(duration_seconds)
                elif vibration_type == 'continuous':
                    self.vibrate_continuous(duration_seconds)
                buzz_timer = tick_time
            elif not elapsed_time >= buzz_delay and self.heartrate_increase_pct >= heartrate_alarm_pct:
                self.vibration_log.info("Heartrate alarm threshold reached ({} percent) but timout not expired".format(self.heartrate_increase_pct))
            else:
                tick_time = time.time()
            time.sleep(0.5)


    def timed_vibration(self, settings):
        interval_minutes = settings['interval_minutes']
        duration_seconds = settings['duration_seconds']
        type = settings['type']
        
        buzz_timer = time.time() 
        tick_time = time.time()
        buzz_delay = interval_minutes * 60

        self.vibration_log.info("Starting vibration timer: {} minutes".format(interval_minutes))

        if type not in ['random', 'pattern', 'rolling', 'continuous']:
            self.vibration_log.warn("Invalid or no vibration type specified: {}".format(type))
            self.vibration_log.warn("Must be one of these: random, pattern, rolling, continuous")
            return

        while True:
            elapsed_time = tick_time - buzz_timer
            if elapsed_time >= buzz_delay:
                print("Buzz timer expired, buzzing")
                if type == 'random':
                    self.vibrate_random(duration_seconds)
                elif type == 'pattern':
                    self.vibrate_pattern(duration_seconds)
                elif type == 'rolling':
                    self.vibrate_rolling(duration_seconds)
                elif type == 'continuous':
                    self.vibrate_continuous(duration_seconds)

                buzz_timer = tick_time
            else:
                tick_time = time.time()
            time.sleep(0.5)


    def generate_random_vibration_pattern(self, pulse_count):
        #pulse_duration_range and pulse_interval_range_ms are arbitrary
        pulse_duration_range = {
                                    'low': 80, 
                                    'high': 120
                                }  
        pulse_interval_range_ms = {
                                    'low': 100, 
                                    'high': 800
                                }

        output_pulse_pattern = []
        for _ in range(pulse_count):
            pulse_duration = random.randrange(pulse_duration_range['low'], pulse_duration_range['high'])
            pulse_interval = random.randrange(pulse_interval_range_ms['low'], pulse_interval_range_ms['high'])/1000
            output_pulse_pattern.append([pulse_duration, pulse_interval])
        return output_pulse_pattern


    def vibrate_random(self, duration_seconds):
        print("Sending random vibration...")
        duration_start = time.time()

        pattern_length = 20  #This value is arbitrary

        pulse_pattern = self.generate_random_vibration_pattern(pattern_length)

        while True:
            if (time.time() - duration_start) >= duration_seconds:
                print ("Stopping vibration")
                self.vibrate_band.vibrate(0)
                break
            else:
                for pattern in pulse_pattern:
                    if (time.time() - duration_start) >= duration_seconds:
                        break
                    vibrate_ms = pattern[0]
                    vibro_delay = pattern[1]
                    self.vibrate_band.vibrate(vibrate_ms)
                    time.sleep(vibro_delay)


    def vibrate_pattern(self, duration_seconds):
        print("Sending vibration...")
        duration_start = time.time()

        #This pattern is an example.
        pulse_pattern = [[30, 0.01], [60, 0.01], [90, 0.01], [120, 0.01], [150, 0.01], [180, 0.01]]

        while True:
            if (time.time() - duration_start) >= duration_seconds:
                print ("Stopping vibration")
                self.vibrate_band.vibrate(0)
                break
            else:
                for pattern in pulse_pattern:
                    if (time.time() - duration_start) >= duration_seconds:
                        break
                    vibrate_ms = pattern[0]
                    vibro_delay = pattern[1]
                    self.vibrate_band.vibrate(vibrate_ms)
                    time.sleep(vibro_delay)


    def vibrate_rolling(self, duration_seconds):
        print("Sending rolling vibration...")

        duration_start = time.time()
        
        while True:
            if (time.time() - duration_start) >= duration_seconds:
                print ("Stopping vibration")
                self.vibrate_band.vibrate(0)
                break
            else:
                for x in range(10):
                    for x in range(20, 40, 1):
                        self.vibrate_band.vibrate(x)
                    for x in range(40, 20, -1):
                        self.vibrate_band.vibrate(x)

    def vibrate_continuous(self, duration_seconds):
        #Currently broken, still working on this bit.
        print("Sending continuous vibration...")

        duration_start = time.time()
        
        while True:
            if (time.time() - duration_start) >= duration_seconds:
                print ("Stopping vibration")
                self.vibrate_band.vibrate(0)
                break
            else:
                self.vibrate_band.vibrate(1)
