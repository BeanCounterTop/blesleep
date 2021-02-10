import pyaudio, time, threading
import numpy as np
from matplotlib import pyplot as plt
import matplotlib.animation as animation


CHUNKSIZE = 1024 # fixed chunk size

# initialize portaudio
p = pyaudio.PyAudio()

info = p.get_host_api_info_by_index(0)
numdevices = info.get('deviceCount')
for i in range(0, numdevices):
    if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
        print("Input Device id ", i, " - ", p.get_device_info_by_host_api_device_index(0, i).get('name'))

stream = p.open(
    format=pyaudio.paInt16, 
    channels=1, 
    rate=44100, 
    input=True, 
    frames_per_buffer=CHUNKSIZE,
    input_device_index=18
    )




plt.style.use('dark_background')
graph_figure = plt.figure()
graph_figure.canvas.set_window_title('blesleep')

graph_axes = graph_figure.add_subplot(1, 1, 1)
graph_data = {}



def graph_animation(i):
    graph_axes.clear()

    graph_axes.plot(numpydata)

ani = animation.FuncAnimation(graph_figure, graph_animation, interval=1000)

def get_audio_data():
    global numpydata
    while True:
        data = stream.read(CHUNKSIZE)
        numpydata = np.frombuffer(data, dtype=np.int16)
        time.sleep(1)


threading.Thread(target=get_audio_data).start()


plt.show()


# close stream
stream.stop_stream()
stream.close()
p.terminate()