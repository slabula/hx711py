# API reference

## Reader API

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

## Channels and gains

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
