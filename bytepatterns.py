
class miband4():

        class bytepatterns():
            vibration = 'ff{:02x}00000001'
            vibration_stop = 'ff0000000000'

            gyro_start = '01{:02x}19'
            start = '0100'
            stop = '0000'
            heart_measure_keepalive = '16'
            stop_heart_measure_continues = '150100'
            start_heart_measure_continues = '150101'
            stop_heart_measure_manual = '150200'
            fetch_begin = '100101'
            fetch_error = '100104'
            fetch_continue = '100201'
            fetch_complete = '100204'
            auth_ok = '100301'
            request_random_number = '0200'
            auth_key_prefix = '0300'

        def vibration(duration):
            if duration == 0:
                byte_pattern = miband4.bytepatterns.vibration_stop
            else:
                byte_pattern = miband4.bytepatterns.vibration
            return bytes.fromhex(byte_pattern.format(duration))

        def gyro_start(sensitivity):
            byte_pattern = miband4.bytepatterns.gyro_start
            return bytes.fromhex(byte_pattern.format(sensitivity))

        start = bytes.fromhex(bytepatterns.start)
        stop = bytes.fromhex(bytepatterns.stop)

        heart_measure_keepalive = bytes.fromhex(bytepatterns.heart_measure_keepalive)
        stop_heart_measure_continues = bytes.fromhex(bytepatterns.stop_heart_measure_continues)
        start_heart_measure_continues = bytes.fromhex(bytepatterns.start_heart_measure_continues)
        stop_heart_measure_manual = bytes.fromhex(bytepatterns.stop_heart_measure_manual)

        fetch_begin = bytes.fromhex(bytepatterns.fetch_begin)
        fetch_error = bytes.fromhex(bytepatterns.fetch_error)
        fetch_continue = bytes.fromhex(bytepatterns.fetch_continue)
        fetch_complete = bytes.fromhex(bytepatterns.fetch_complete)

        auth_ok = bytes.fromhex(bytepatterns.auth_ok)
        request_random_number = bytes.fromhex(bytepatterns.request_random_number)
        auth_key_prefix = bytes.fromhex(bytepatterns.auth_key_prefix)
        