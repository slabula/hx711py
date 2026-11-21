# HX711 for Raspberry Pi

A Python library for reading HX711 load-cell amplifiers on a Raspberry Pi, with
a built-in emulator for development on any machine. It provides signed 24-bit
raw readings, calibrated weight readings, channel/gain selection, optional
filtering, an HTTP JSON server, and `timestamp,weight` streaming over a Pi Zero
W USB serial gadget.

The implementation is derived from
[underdoeg's HX711.py gist](https://gist.github.com/underdoeg/98a38b54f889fce2b237).
The original project is [tatobari/hx711py](https://github.com/tatobari/hx711py).
The current implementation is `hx711/core.py`; `hx711/v0_5_1.py` is deprecated.

## Documentation

Full documentation lives in [`docs/`](docs/README.md):

- [Getting started](docs/getting-started.md) — caveats, wiring, installation, and first readings
- [API reference](docs/api.md) — reader API, calibration, filtering, and sample-rate measurement
- [HTTP server](docs/server.md) — JSON endpoint, options, and HTTP client
- [USB serial streaming](docs/usb-serial.md) — Pi Zero W OTG setup, serial client, permissions, and systemd
- [Emulator](docs/emulator.md) — hardware-free testing
- [Emulator review](docs/emulator-review.md) — fake GPIO/HX711 implementation review
- [Development](docs/development.md) — tests, project layout, and the deprecated driver
- [Improvement backlog](docs/improvement-backlog.md) — ranked remaining suggestions
- [Changelog](docs/changelog.md)

## Quick example

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

On a machine without `RPi.GPIO`, each `HX711` instance automatically gets its
own fake GPIO/HX711 emulator.

## Server quick start

```bash
# HTTP JSON server
python hx711_server.py --unit kg --m 0.000018 --c -2.5
python example_client.py --url http://raspberrypi.local:8080/weight
python example_client.py --url http://raspberrypi.local:8080/weight --csv samples.csv

# Pi Zero W USB serial stream
python hx711_server.py --serial /dev/ttyGS0 --unit kg --m 0.000018 --c -2.5
python example_client.py --serial /dev/ttyACM0 --unit kg
python example_client.py --serial /dev/ttyACM0 --unit kg --csv samples.csv
```

See [HTTP server](docs/server.md) and [USB serial streaming](docs/usb-serial.md)
for setup details.

## License

Apache License 2.0. See [LICENSE](LICENSE).
