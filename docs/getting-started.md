# Getting started

## Caveats

Reading the HX711 is timing-sensitive. Linux on a Raspberry Pi is not a
real-time operating system, so GPIO operations can be delayed or run too fast.
That can produce corrupt or random readings when the system is busy.

For dependable timing, consider using a microcontroller to read the HX711 and
send results to the Pi over I2C, 1-Wire, or another link. This library is useful
for hobby projects, but test it in your environment before relying on it.

The optional `PigpioHX711` backend uses pigpio daemon waveforms for the PD_SCK
clock, so the critical clock edges are generated in hardware rather than by
Python. It still uses Linux callbacks to detect when a conversion is ready. The
original pigpio daemon does not support Raspberry Pi 5; use Pi 1-4 or a
microcontroller for that board.

A local comparison did not show pigpio as a clear accuracy win: it ran slower
and reduced the glitch percentage only slightly. See
[Backend comparison](api.md#backend-comparison).

## Hardware

Connect the HX711 to the Raspberry Pi according to your breakout board's
datasheet. This library uses **BCM** pin numbering. The examples use:

- `DOUT` / `DT` -> BCM 5
- `PD_SCK` / `SCK` -> BCM 6

Change the constructor arguments if your wiring is different. Make sure the
HX711 and Raspberry Pi share a common ground. The HX711 runs at 10 samples per
second by default, or 80 samples per second when the RATE pin is tied high.

For USB serial streaming on a Pi Zero W, see
[USB serial streaming](usb-serial.md).

## Installation

```bash
git clone https://github.com/slabula/hx711py.git
cd hx711py
pip install .
```

On a Raspberry Pi, install the GPIO dependency with:

```bash
pip install .[rpi]
```

For hardware-timed PD_SCK clocking with pigpio, install the backend and start
the daemon:

```bash
pip install .[pigpio]
sudo pigpiod
```

For development and tests:

```bash
pip install -e .[dev]
```

## Quick start

Read raw signed 24-bit values:

```python
from hx711 import HX711

hx = HX711(dout=5, pd_sck=6)

try:
    hx.reset()

    while True:
        raw = hx.read_word()
        if raw is not None:
            print(raw)
except KeyboardInterrupt:
    pass
finally:
    hx.cleanup()
```

`read_word()` and `read_weight()` return `None` when a read times out.

To use hardware-generated PD_SCK pulses with pigpio:

```python
from hx711 import PigpioHX711

hx = PigpioHX711(dout=5, pd_sck=6)

try:
    raw = hx.read_word()
finally:
    hx.cleanup()
```

For calibrated readings, set `m` and `c` before reading:

```python
from hx711 import HX711

hx = HX711(dout=5, pd_sck=6)

try:
    hx.reset()
    hx.set_m(0.000018)
    hx.set_c(-2.5)

    while True:
        weight = hx.read_weight()
        if weight is not None:
            print(weight)
except KeyboardInterrupt:
    pass
finally:
    hx.cleanup()
```

Without calibration, `m=1.0` and `c=0.0`, so `read_weight()` returns the raw
value.

On a machine without `RPi.GPIO`, each `HX711` instance automatically gets its
own fake GPIO/HX711 emulator. To feed it known samples, inject a `FakeHx711`
through `gpio_module` as shown in [Emulator](emulator.md).
