# MicroPython Plotter: Quick Start Guide

This library helps you visualize data from your MicroPython device instantly. Follow these steps to get started.

### Installation

Before coding, you need to put the library on your device.

1. Install `mpremote` package in your python environment 

2. Use the `install.sh` or `install.cmd` script 

or:

1. Connect your device to your computer.

2. Open Thonny.

3. Upload the `mp_plotter.py` file to the **`lib`** folder on your device.



### How to Use in Code

Using the plotter is very easy. 

1. Import the library in the file you want to use

   ```python
   from mp_plotter import plotter
   ```

2. Call `plotter.plot()` to plot. It should be called at only one place, otherwise the computer side will confuse about the data. Of course it can be in the loop, but only at one place. 

   A correct example:

   ```python
   import time
   from mp_plotter import plotter
   
   value1 = 0
   value2 = 0
   plotter.plot(value1, value2)
   
   for i in range (10000):
   	plotter.plot(i, 2i, 3i)
     time.sleep(0.05)
   ```

   But not:

   ```python
   from mp_plotter import plotter
   
   value1 = 0
   value2 = 0
   plotter.plot(value1, value2)
   
   for i in range(10000):
     plotter.plot(i, 2i, 3i)
   	for j in range(100):
     	plotter.plot(j)	# two plotter calls, which will mess up the data sent to computer
   		time.sleep(0.05)
   ```

   

### Notes

- **Data Types:** You can plot integers (`int`) or decimals (`float`). Note that `float` values are automatically converted to integers before sending. In the future more type will be supported.
- **Limit:** You can plot a maximum of 5 variables at the same time.
- **Visualizing:** Open the micropython-plotter software to see your graphs in real-time using `Plot` tool.

- **On macOS**: You might receive a warning about the application and can't open it, open the `terminal` and run `xattr -d com.apple.quarantine <path-to-micropython-plotter>`, change the path to your actual path and name such as `micropython-plotter_macos_arm64.app`

### About `print()`

To make the plotting fast and smooth, this library **disables the standard Python `print()` function** by default. Namely:

- **If you use `print()`:** Nothing will happen.
- **If you need to debug text:** Use `plotter.print("hello")` instead.
- **If you want to enable the original print():** You can turn it back on by running `plotter.restore_print()` anytime after importing the library.