class Sleep_Data(object):
    def __init__(self):
        print("init")

        
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