import numpy as np
import matplotlib.pyplot as plt
x = np.arange(0, 10, 0.1)
y1 = 0.05 * x**2
y2 = -1 *y1

fig, ax1 = plt.subplots()



ax2 = ax1.twinx()
figures=[manager.canvas.figure
         for manager in plt._pylab_helpers.Gcf.get_all_fig_managers()]
print(figures)

ax1.plot(x, y1, 'g-')
ax2.plot(x, y2, 'b-')

plt.show()