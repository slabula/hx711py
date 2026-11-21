# Changelog

## 2026-11-21

- Added `NoFilter`, `MedianFilter`, `ExponentialFilter`,
  `MedianExponentialFilter`, `HampelFilter`, and `HampelExponentialFilter`.
- `SampleFilter` is now a backwards-compatible alias for
  `MedianExponentialFilter`.
- `hx711_server.py` gained a `--filter` selector with `none`, `median`, `ema`,
  `median-ema`, `hampel`, and `hampel-ema` choices, plus Hampel tuning options.
- Existing `--filter-cutoff` usage still selects `median-ema`.
- `--filter-window` was added as the preferred name for `--filter-median-window`.
- `example_client.py` now estimates sample rate from timestamps instead of
  de-duplicating repeated weights, so filtered/stable loads report the correct
  rate.

## 2026-11-20

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
- `example_client.py` now prints the sample rate derived from unique values in
  the server's recent samples.
- Added optional `timestamp,weight` streaming over a USB ACM serial port with
  `--serial`, plus Pi Zero W gadget setup documentation and a systemd example.
- `example_client.py` can now read the serial stream with `--serial`, skipping
  malformed or partial samples.
- Documentation was split into topic files under `docs/`.

## 2026-11-14

- Added optional `SampleFilter` settings to `hx711_server.py`: `--filter-cutoff`, `--filter-sample-rate`, and `--filter-median-window`.
- `hx711_server.py` now stops its reader thread before releasing GPIO on shutdown.
- Calibration and filter setters now synchronize with reads through the same lock.
- README reorganized with installation, API, calibration, filtering, server, and emulator documentation.

## 2026-11-13

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

## 2023-03-03

- Changed the filename of the new version to make a bit more sense (Sorry for not making a new branch for the new version.).
- Added example file for v0.5.1.
- Added GIF examples of new library to README.md.
- Added example commands to README.md.
- **Tested v0.5.1 and working.**

## 2023-02-28

I'm only using my lunch time to commit changes in order to close all the HX711 environment on my mac because I need more processing power.

This version adds new methods to allow the use of interrupts as an alternative to polling.

## 2024-02-25

Funnily enough and by pure accident, exactly two years after updating the README.md file with false promises, I'm back making a few changes.

My motivation to update this code is to improve the reading frequency.

## 2021-02-25

For the past years I haven't been able to maintain this library because I had too much workload. Now I'm back and I've been working on a few fixes and modifications to simplify this library, and I might be committing the branch by mid-March. I will also publish it to PyPI.
