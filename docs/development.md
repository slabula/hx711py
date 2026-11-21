# Development

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
| `example_client.py` | Server polling client, with serial mode |
| `dummy_scale_server.py` | CSV replay server for client testing |
| `hx711/v0_5_1.py` | Deprecated previous implementation |
| `example_hx711v0_5_1.py` | Example for the deprecated version |
| `docs/` | Topic-based documentation |
| `resources/` | Images, PDFs, and the example systemd unit |
| `tests/` | Pytest test suite |

## Deprecated version

`hx711/v0_5_1.py` is deprecated in favor of `hx711/core.py` and is kept for
backwards compatibility only. It supports interrupt-based and polling-based
reads:

```bash
python example_hx711v0_5_1.py
python example_hx711v0_5_1.py --polling-based
```

Legacy screenshots are available in the [`resources`](../resources) directory.
