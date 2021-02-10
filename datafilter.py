import time, os, csv
from datetime import datetime
from matplotlib import pyplot as plt

datapath = '/home/daddy/Projects/miband/data/2021_02_07/'
window_min = 30
figure_height = 9
figure_width = 18
fullscreen = False


files = os.listdir(datapath)
wavs = []
csvs = []
for file in files:
    if 'wav' in file:
        wavs.append(file)
    elif 'csv' in file and 'raw' in file:
        csvs.append(file)


event_data_list = []
for wav in wavs:
    event_dict = {
        'name': wav,
        'data': {
            'mov_x': [],
            'mov_y': [],
            'bpm_x': [],
            'bpm_y': []
            }
        }

    wavtime = datetime.strptime(wav, '%Y_%m_%d__%H_%M_%S.wav')
    wavestamp = wavtime.timestamp()

    plotdata_mov_x = []
    plotdata_mov_y = []
    plotdata_bpm_x = []
    plotdata_bpm_y = []
    for mycsv in csvs:
        with open((datapath + mycsv), newline='') as csvfile:
            csvreader = csv.DictReader(csvfile, delimiter=',')
            for row in csvreader:
                if abs((float(wavestamp) - float(row['time']))) <= (window_min * 60):
                    if 'bpm' in row:
                        event_dict['data']['bpm_x'].append( int(row['bpm']) )
                        event_dict['data']['bpm_y'].append( datetime.fromtimestamp(float(row['time'])) )
                    elif 'movement' in row:
                        event_dict['data']['mov_x'].append( int(row['movement']) )
                        event_dict['data']['mov_y'].append( datetime.fromtimestamp(float(row['time'])) )

    event_data_list.append(event_dict)


for event_data in event_data_list:
    event_name = event_data['name'].rsplit('.', 1)[0]
    output_png_filename = '{}{}'.format(event_name, ".png")
    data = event_data['data']
    plt.close("all")
    
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    ax.plot(data['bpm_y'], data['bpm_x'], color="red")
    ax2.plot(data['mov_y'], data['mov_x'], color="blue")

    fig.set_figheight(figure_height)
    fig.set_figwidth(figure_width)
    fig.autofmt_xdate()

    if fullscreen:
        plt.get_current_fig_manager().full_screen_toggle()
    plt.title(event_name)
    if data['bpm_y']:
        plt.savefig(datapath + output_png_filename)
        plt.show()