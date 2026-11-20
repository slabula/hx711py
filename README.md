# HX711 for Raspberry Pi

A Python library for reading HX711 load-cell amplifiers on a Raspberry Pi, with
a built-in emulator for development on any machine. It provides signed 24-bit
raw readings, calibrated weight readings, channel/gain selection, optional
filtering, and an HTTP JSON server.

The implementation is derived from
[underdoeg's HX711.py gist](https://gist.github.com/underdoeg/98a38b54f889fce2b237).
The original project is [tatobari/hx711py](https://github.com/tatobari/hx711py).
The current implementation is `hx711/core.py`; `hx711/v0_5_1.py` is deprecated.

## Contents

- [Caveats](#caveats)
- [Hardware](#hardware)
- [Installation](#installation)
- [Quick start](#quick-start)
- [API](#api)
- [Calibration](#calibration)
- [Filtering](#filtering)
- [Sample rate](#sample-rate)
- [HTTP server](#http-server)
- [Replay fake data from CSV](#replay-fake-data-from-csv)
- [Hardware-free emulator](#hardware-free-emulator)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Deprecated version](#deprecated-version)
- [Changelog](#changelog)
- [License](#license)

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
and reduced the glitch percentage only slightly. See [Backend comparison](#backend-comparison).

## Hardware

Connect the HX711 to the Raspberry Pi according to your breakout board's
datasheet. This library uses **BCM** pin numbering. The examples use:

- `DOUT` / `DT` -> BCM 5
- `PD_SCK` / `SCK` -> BCM 6

Change the constructor arguments if your wiring is different. Make sure the
HX711 and Raspberry Pi share a common ground. The HX711 runs at 10 samples per
second by default, or 80 samples per second when the RATE pin is tied high.

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

On a machine without `RPi.GPIO`, the library automatically uses the fake
GPIO/HX711 emulator and prints a message when imported.

## API

| API | Description |
| --- | --- |
| `HX711(dout, pd_sck, gpio_module=None)` | Create a reader. `gpio_module` lets you inject a fake or alternate GPIO implementation. |
| `PigpioHX711(dout, pd_sck, pi=None, pigpio_module=None, close_pi=None)` | Read through pigpio using a hardware-timed PD_SCK waveform. Requires `pigpiod`. |
| `read_word(timeout_seconds=0.5)` | Return one signed 24-bit value, or `None` on timeout. |
| `read_weight(timeout_seconds=0.5)` | Read, apply `m`/`c`, and apply the optional filter. Returns `None` on timeout. |
| `set_m(m)`, `set_c(c)` | Set calibration values. Resets an attached filter. |
| `set_filter(filter)` | Attach a filter; use `set_filter(None)` to remove it. |
| `set_channel_gain(value)`, `get_channel_gain()` | Select channel/gain. Invalid values raise `ValueError`. |
| `is_ready()` | Return `True` when a conversion is ready. |
| `power_down()`, `power_up()`, `reset()`, `cleanup()` | Power management and GPIO cleanup. |

Read, calibration, filter, channel, and power methods share a reentrant lock,
so a single `HX711` instance can be used from multiple threads. Call
`cleanup()` only after reads have stopped.

### Channels and gains

| Constant | Channel | Gain | PD_SCK pulses |
| --- | --- | --- | --- |
| `CH_A_GAIN_128` | A | 128 | 25 |
| `CH_B_GAIN_32` | B | 32 | 26 |
| `CH_A_GAIN_64` | A | 64 | 27 |

`set_channel_gain()` reads and discards the pending conversion so that the next
conversion uses the requested channel/gain. Channel B has a fixed gain of 32;
channel A supports gains of 128 and 64. The two channels differ in accuracy.

## Calibration

`calibrate_sensor.py` walks you through measuring one or more known loads and
fits `load = m * raw + c`:

```bash
python calibrate_sensor.py --unit kg
```

Enter a known load, let the scale settle, and press Enter to measure. Leave the
load blank to finish. With at least two different loads it prints the
calibration values and the lines to paste into your program:

```python
hx.set_m(m)
hx.set_c(c)
weight = hx.read_weight()
```

Use `--samples` to change the number of raw samples taken per load, and `--gain`
to select the channel/gain. Run `python calibrate_sensor.py --help` for all
options.

## Filtering

`SampleFilter` smooths calibrated readings. It takes the median of the last few
samples to reject spikes, then applies a first-order low-pass filter:

```python
from hx711 import HX711, SampleFilter

hx = HX711(5, 6)
hx.set_m(m)
hx.set_c(c)
hx.set_filter(SampleFilter(80.0, 10.0))
weight = hx.read_weight()
```

The first argument is the actual sample rate in Hz and the second is the desired
cutoff in Hz. `median_window` defaults to 5.

The smoothing coefficient is:

```text
alpha = 1 - exp(-2 * pi * cutoff * dt)
```

This exponential mapping gives a cutoff much closer to the requested value than
the backward-Euler approximation, though it can drift slightly when the cutoff
is a large fraction of the sample rate.

Make sure the sample rate matches your setup. The HX711 normally runs at 10 SPS,
or 80 SPS with RATE tied high; `measure_sample_rate.py` reports the rate you
actually achieve. `SampleFilter.reset()` clears the filter state, and `set_m()`
and `set_c()` reset an attached filter automatically.

## Sample rate

Use `measure_sample_rate.py` to measure the rate you actually achieve:

```bash
python measure_sample_rate.py
python measure_sample_rate.py --gpio pigpio --dout 5 --pd-sck 6 --seconds 30
python measure_sample_rate.py --legacy
```

It runs for 60 seconds by default and reports the mean, minimum, and maximum
sample rate, plus dropped reads. `--gpio` selects the `rpi` (default) or
`pigpio` HX711 backend. Use `--samples-per-batch` to change how many reads are
timed together.

`--legacy` uses the deprecated `hx711.v0_5_1` driver and its polling
`getLong()` method instead of the current `read_word()` driver. It only supports
RPi.GPIO, so it cannot be combined with `--gpio pigpio`.

The script also collects successful raw samples and computes the median and
median absolute deviation (MAD) for each batch and overall. A glitch is any
sample whose absolute deviation from the median is greater than
`max(--glitch-threshold, --glitch-mad-scale * MAD)`. The output reports glitch
count, percentage, and total/mean/maximum magnitude in raw counts. Lowering the
threshold makes detection more sensitive.

### Backend comparison

A 60-second run of each method is recorded in `comparison.txt` and
`legacy.txt`:

| Method | Mean rate | Dropped | Glitches | Mean glitch magnitude | Max glitch magnitude |
| --- | --- | --- | --- | --- | --- |
| `--gpio rpi` | 77.26 Hz | 0 | 57 / 4600 (1.24%) | 1.01e6 | 8.32e6 |
| `--legacy` | 73.96 Hz | 0 | 60 / 4400 (1.36%) | 1.35e6 | 8.31e6 |
| `--gpio pigpio` | 54.15 Hz | 0 | 36 / 3300 (1.09%) | 4.24e6 | 8.44e6 |

The current RPi.GPIO backend was the fastest and had slightly fewer glitches
than the legacy polling method. The legacy method ran a little slower and had a
slightly higher glitch rate. Pigpio was about 30% slower than the current
RPi.GPIO backend but only reduced the glitch rate from 1.24% to 1.09%, with a
higher mean glitch magnitude.

All three methods still produced comparable large spikes, including maximum
glitches around 8.3e6 raw counts. None of these read methods is a guaranteed
fix; keep using the median/MAD glitch statistics to judge your own setup.

## HTTP server

`hx711_server.py` reads the HX711 in a background thread and serves up to the
latest 100 calibrated readings as JSON over HTTP:

```bash
python hx711_server.py --unit kg --m 0.000018 --c -2.5
```

Then poll it from another machine:

```bash
python example_client.py --url http://raspberrypi.local:8080/weight
```

`GET /weight` (or `GET /`) returns:

```json
{
  "ts": 1794601083.345,
  "weight": 12.47,
  "unit": "kg",
  "samples": [
    {"ts": 1794601082.912, "weight": 12.31, "unit": "kg"},
    {"ts": 1794601083.345, "weight": 12.47, "unit": "kg"}
  ]
}
```

The top-level fields still describe the latest reading, so existing clients keep
working. `samples` contains up to 100 readings, oldest first.

| Field | Meaning |
| --- | --- |
| `ts` | UTC epoch seconds |
| `weight` | Calibrated reading, filtered if enabled |
| `unit` | Unit label |
| `samples` | Up to 100 recent reading objects with `ts`, `weight`, and `unit` |

The server returns `503` until the first reading is available. It has no
authentication, so only expose it on a trusted network.

### Server options

| Option | Default | Description |
| --- | --- | --- |
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `8080` | TCP port |
| `--dout` | `5` | DOUT GPIO pin |
| `--pd-sck` | `6` | PD_SCK GPIO pin |
| `--gpio` | `rpi` | GPIO backend: `rpi` or `pigpio` |
| `--gain` | `128` | Channel A gain 128/64, or channel B gain 32 |
| `--m` | `1.0` | Calibration `m` |
| `--c` | `0.0` | Calibration `c` |
| `--unit` | `units` | Unit label reported to clients |
| `--filter-cutoff` | disabled | Enable the low-pass filter at this cutoff in Hz |
| `--filter-sample-rate` | `80` | Expected sample rate for filtering, in Hz |
| `--filter-median-window` | `5` | Median window size |

To enable filtering:

```bash
python hx711_server.py --m 0.000018 --c -2.5 --filter-cutoff 5 --filter-sample-rate 80
```

Set `--filter-sample-rate` to the actual read rate for your hardware. Without
`--filter-cutoff`, readings are unfiltered.

### Replay fake data from CSV

`dummy_scale_server.py` in the repository root replays a two-column
`timestamp,weight` CSV through the same `GET /weight` payload as
`hx711_server.py`, so you can test HX711 JSON clients without hardware:

```bash
python3 dummy_scale_server.py live.csv --loop --start-delay 5
```

Timestamps are scheduling marks in seconds; relative and epoch timestamps both
work because only differences matter. Use `--speed` to compress long files.
Add a few seconds of zero load at the start of the CSV if the session should
begin from rest. When the file ends the last reading is held; `--loop` repeats
it. `--start-delay` holds the first reading while clients connect and tare.

| Option | Default | Description |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8080` | TCP port |
| `--unit` | `kg` | Unit label |
| `--speed` | `1.0` | Replay speed multiplier |
| `--loop` | off | Restart the file when it ends |
| `--start-delay` | `0` | Hold the first reading for this many seconds |

## Hardware-free emulator

When `RPi.GPIO` is unavailable, the library automatically uses `FakeGpio` and
`FakeHx711`, so imports and examples still work. `example_emulator.py` shows how
to inject your own samples:

```bash
python example_emulator.py
```

For explicit control:

```python
from hx711 import HX711
from hx711.fake_gpio import FakeGpio
from hx711.fake_hx711 import FakeHx711

fake_hx711 = FakeHx711()
fake_hx711.inject_raw_samples([0, 1000, 2000])

hx = HX711(5, 6, gpio_module=FakeGpio(fake_hx711))
hx.reset()

print(hx.read_word())
```

The emulator is intended for software testing, not for validating real timing.
It currently supports only channel A gain 128; selecting channel B gain 32 or
channel A gain 64 raises an error in the emulator.

## Testing

```bash
pip install -e .[dev]
python -m pytest
```

The tests run without Raspberry Pi hardware by using the fake GPIO/HX711.

## Project layout

| Path | Purpose |
| --- | --- |
| `hx711/core.py` | Main `HX711` implementation |
| `hx711/pigpio_hx711.py` | Optional pigpio hardware-timed backend |
| `hx711/sample_filter.py` | Median + exponential-moving-average filter |
| `hx711/fake_gpio.py`, `hx711/fake_hx711.py` | Fake GPIO/HX711 for development |
| `hx711/__init__.py` | Package exports: `HX711`, `SampleFilter` |
| `example.py` | Calibrated, filtered reading example |
| `example_emulator.py` | Explicit emulator example |
| `calibrate_sensor.py` | Interactive calibration helper |
| `measure_sample_rate.py` | Sample-rate measurement utility |
| `hx711_server.py` | HTTP JSON server |
| `example_client.py` | Server polling client |
| `hx711/v0_5_1.py` | Deprecated previous implementation |
| `example_hx711v0_5_1.py` | Example for the deprecated version |
| `tests/` | Pytest test suite |

## Deprecated version

`hx711/v0_5_1.py` is deprecated in favor of `hx711/core.py` and is kept for
backwards compatibility only. It supports interrupt-based and polling-based
reads:

```bash
python example_hx711v0_5_1.py
python example_hx711v0_5_1.py --polling-based
```

Legacy screenshots are available in the [resources](resources) directory.

## Changelog

### 20/11/2026

- Added `PigpioHX711`, an optional backend that uses pigpio daemon waveforms for
  hardware-timed PD_SCK pulses.
- Added the `pigpio` install extra and `--gpio pigpio` to the server,
  calibration helper, and sample-rate script.
- Added `--dout`, `--pd-sck`, `--seconds`, and `--samples-per-batch` options to
  `measure_sample_rate.py`.
- `measure_sample_rate.py` now collects raw samples and reports median/MAD-based
  glitch counts and magnitudes, tunable with `--glitch-threshold` and
  `--glitch-mad-scale`.
- Documented the local backend comparison: pigpio was slower and did not reduce
  glitches proportionally.
- `hx711_server.py` now keeps the latest 100 readings and serves them in the
  `/weight` JSON response as `samples`.
- `measure_sample_rate.py` now supports `--legacy` to measure with the old
  `hx711.v0_5_1` polling method.

### 14/11/2026

- Added optional `SampleFilter` settings to `hx711_server.py`: `--filter-cutoff`, `--filter-sample-rate`, and `--filter-median-window`.
- `hx711_server.py` now stops its reader thread before releasing GPIO on shutdown.
- Calibration and filter setters now synchronize with reads through the same lock.
- README reorganized with installation, API, calibration, filtering, server, and emulator documentation.

### 13/11/2026

- Restructured the library into the `hx711/` package; utility scripts at the top level import from it.
- `hx711/core.py` is now the main implementation; `hx711/v0_5_1.py` is deprecated.
- Removed the old simulated emulator; `hx711/fake_gpio.py` and `hx711/fake_hx711.py` remain for running without hardware.
- Added GPIO injection via `gpio_module=` and an `HX711.cleanup()` method.
- `set_channel_gain()` now validates its argument and raises `ValueError` for invalid values.
- Added `set_m()`, `set_c()`, and `read_weight()` for calibrated weight readings.
- Added `calibrate_sensor.py` to fit `m` and `c` from known loads.
- Added `hx711/sample_filter.py` with an optional median + EMA filter using an exponential alpha mapping, exported as `SampleFilter`.
- Added `hx711_server.py` and `example_client.py` for serving readings over HTTP.
- Added `measure_sample_rate.py` and a `pytest` test suite.
- `RPi.GPIO` is now an optional `rpi` extra, so the package installs off-Pi.

### 03/03/2023

- Changed the filename of the new version to make a bit more sense (Sorry for not making a new branch for the new version.).
- Added example file for v0.5.1.
- Added GIF examples of new library to README.md.
- Added example commands to README.md.
- **Tested v0.5.1 and working.**

### 28/02/2023

I'm only using my lunch time to commit changes in order to close all the HX711 environment on my mac because I need more processing power.

This version adds new methods to allow the use of interrupts as an alternative to polling.

### 25/02/2023

Funnily enough and by pure accident, exactly two years after updating the README.md file with false promises, I'm back making a few changes.

My motivation to update this code is to improve the reading frequency.

### 25/02/2021

For the past years I haven't been able to maintain this library because I had too much workload. Now I'm back and I've been working on a few fixes and modifications to simplify this library, and I might be committing the branch by mid-March. I will also publish it to PyPI.

## License

Apache License 2.0. See [LICENSE](LICENSE).
