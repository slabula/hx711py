# HTTP server

`hx711_server.py` reads the HX711 in a background thread and serves up to the
latest 100 calibrated readings as JSON over HTTP:

```bash
python hx711_server.py --unit kg --m 0.000018 --c -2.5
```

Then poll it from another machine:

```bash
python example_client.py --url http://raspberrypi.local:8080/weight
```

The client also prints the sample rate estimated from the server's `samples`
list. Repeated `weight` values are counted once, and the remaining unique sample
count is divided by the timestamp span. Servers that do not provide samples
show `rate n/a`.

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

## Server options

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
| `--serial` | disabled | Also stream `timestamp,weight` lines to this device |
| `--serial-baudrate` | `115200` | Serial baud rate (ignored by USB ACM) |
| `--filter-cutoff` | disabled | Enable the low-pass filter at this cutoff in Hz |
| `--filter-sample-rate` | `80` | Expected sample rate for filtering, in Hz |
| `--filter-median-window` | `5` | Median window size |

To enable filtering:

```bash
python hx711_server.py --m 0.000018 --c -2.5 --filter-cutoff 5 --filter-sample-rate 80
```

Set `--filter-sample-rate` to the actual read rate for your hardware. Without
`--filter-cutoff`, readings are unfiltered.

## Related guides

- [USB serial streaming](usb-serial.md) — stream `timestamp,weight` lines over a Pi Zero W USB gadget port.
- [Emulator](emulator.md) — test client code without hardware using fake GPIO/HX711 classes.
- [USB serial streaming](usb-serial.md#run-the-server-at-boot) — start the server automatically with systemd.
